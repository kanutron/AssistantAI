import json
import threading
import sublime
import http.client
from typing import Optional, Dict, List, Any, Union
from urllib.parse import urlparse, urlencode
from .assistant_settings import AssistantAISettings, Endpoint, Prompt

class AssistantThread(threading.Thread):
    """
    An async thread class for accessing the remote server API, and waiting for a response
    """
    timeout: int
    running: bool
    result: Optional[dict]
    settings: AssistantAISettings
    prompt: Prompt
    endpoint: Endpoint
    region: sublime.Region
    stack: List[dict]
    # thread attribs coming from given prompt
    variables: Dict[str, str]
    data: Dict[str, Any]
    query: str
    conn: Union[http.client.HTTPConnection, http.client.HTTPSConnection]

    def __init__(self, settings: AssistantAISettings, prompt: Prompt, endpoint: Endpoint,
                 region: sublime.Region, text: str, pre: str, post: str, stack: List[dict], kwargs: dict):
        super().__init__()
        self.timeout = endpoint.timeout if endpoint.timeout else 60
        self.running = False
        self.result = None
        self.settings = settings
        self.prompt = prompt
        self.endpoint = endpoint
        self.region = region
        self.stack = stack
        # prompt vars may add text
        self.variables = self.prepare_vars(text, pre, post, kwargs)
        self.data = self.prepare_data()
        self.query = self.prepare_query()
        self.conn = self.prepare_conn()
        # if the command spec from prompt forces a syntax, take that
        # otherwise, use the prompt var (i.e.: current syntax), or 'Markdown'
        if 'syntax' not in self.prompt.command:
            self.prompt.command['syntax'] = self.variables.get('syntax', 'Markdown')

    def prepare_vars(self, text: str, pre: str, post: str, kwargs: dict) -> Dict[str, str]:
        """
        Prepares variables to be used in a prompt.

        Args:
            text (str): The text to be displayed in the prompt.
            pre (str): The pre-text before text.
            post (str): The post-text after text.
            kwargs (dict): Any additional keyword arguments to be used.

        Returns:
            dict: The updated dictionary of variables.
        """
        # build base vars as provided by prompt command
        vars_: Dict[str, str] = {
            "text": text,
            "pre": pre,
            "post": post,
        }
        vars_.update(kwargs)
        # expand vars as defined by prompt/vars
        for k, v in self.prompt.variables.items():
            # for convenience, in vars, user may specify
            # each line as a string of an array
            if isinstance(v, list):
                v = '\n'.join(v)
            vars_[k] = str(sublime.expand_variables(v, vars_))
        return vars_

    def prepare_data(self) -> Dict[str, Any]:
        """
        This function prepares data to be sent to an API endpoint.

        Returns:
            data (dict): A dictionary containing the prepared data.
        """
        request: Dict[str, Any] = {}
        request.update(self.endpoint.request)
        request.update(self.prompt.params)
        for k, v in request.items():
            request[k] = sublime.expand_variables(v, self.variables)
        to_filter = set()
        for k, v in request.items():
            if k not in self.endpoint.valid_params:
                to_filter.add(k)
                print(f"AssistantAI: WARNING: '{self.prompt.pid}' provides a param '{k}' not accepted by '{self.endpoint.eid}'.")
            # TODO: check valid_params specified type.
        return {k:v for k,v in request.items() if k not in to_filter}

    def prepare_query(self) -> str:
        """
        This function prepares query string to be sent to an API endpoint.

        Returns:
            query (string): A URL encoded string containing the prepared payload.
        """
        query: Dict[str, str] = {}
        query.update(self.endpoint.query)
        query.update(self.prompt.query)
        data: Dict[str, str] = {}
        for k, v in query.items():
            data[k] = str(sublime.expand_variables(v, self.variables))
        return urlencode(data)

    def prepare_conn(self) -> Union[http.client.HTTPConnection, http.client.HTTPSConnection]:
        """
        Prepares the HTTP connection based on the endpoint URL.

        Returns:
        http.client.HTTPConnection or http.client.HTTPSConnection: The suitable HTTP connection to be used for
        sending requests to the endpoint URL.
        """
        url = urlparse(self.endpoint.url)
        scheme = str(url.scheme)
        hostname = str(url.hostname)
        port = url.port
        if not url.port:
            port = 443 if scheme == 'https' else 80
        if scheme == 'https':
            # TODO: we should allow connect to servers with custom CA certificates and using client certificates
            return http.client.HTTPSConnection(hostname, port=port)
        return http.client.HTTPConnection(hostname, port=port)

    def run(self) -> None:
        self.running = True
        self.result = self.get_response()
        self.running = False

    def get_response(self) -> Dict[str, Any]:
        """
        Pass the given data to remote API, returning the response
        """
        data = json.dumps(self.data)
        method = self.endpoint.method
        resource = self.endpoint.resource
        resource = str(sublime.expand_variables(resource, self.variables))
        if self.query:
            resource = f"{resource}?{self.query}"
        headers = self.endpoint.headers if self.endpoint.headers else {}
        self.conn.request(method, resource, data, headers)
        response = self.conn.getresponse()
        return self.parse_response(json.loads(response.read().decode()))

    def parse_response(self, data: dict) -> Dict[str, Any]:
        """
        This function takes in a dictionary 'data' and parses it according to a template defined in 'self.endpoint'.
        It returns a dictionary with keys corresponding to the keys in the template and corresponding values either from the parsed 'data'
        or an error message if any error occurred while parsing
        """
        response: Dict[str, Any] = {}
        template = self.endpoint.response
        if not template:
            response['error'] = f"The endpoint doesn't specify any reponse template."
            return response
        for k, path in template.items():
            item = self.get_item(data, str(path))
            if item is None and k != 'error':
                response['error'] = f"Error getting response item {k} in '{path}'"
            response[k] = item
        response['response'] = data
        return response

    def get_item(self, data: Optional[dict], path: str) -> Optional[Any]:
        """Returns the value located at the end of a given path within a nested data structure.

        Args:
            data (list/dict/tuple): The nested data structure to search for the value.
            path (str): The path to the desired value within the data structure, separated by forward slashes.

        Returns:
            The value located at the end of the path within the data structure, or None if not found.
        """
        if not path:
            return data
        parts = path.split('/')
        if len(parts) == 0:
            return data
        if not isinstance(data, (list, dict, tuple)):
            return data
        part = parts.pop(0)
        if part.isnumeric() and isinstance(data, (list, tuple)):
            part = int(part)
            if len(data) > part:
                return self.get_item(data[part], '/'.join(parts))
        elif isinstance(data, dict):
            return self.get_item(data.get(part), '/'.join(parts))
        return None
