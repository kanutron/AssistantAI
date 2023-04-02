import json
import threading
import http.client
from urllib.parse import urlparse, urlencode
import sublime


class AssistantThread(threading.Thread):
    """
    An async thread class for accessing the remote server API, and waiting for a response
    """
    timeout = 60
    running = False
    result = None

    def __init__(self, settings, prompt, endpoint, region, text, pre, post, kwargs):
        super().__init__()
        self.settings = settings
        self.prompt = prompt
        self.endpoint = endpoint
        self.region = region
        # prompt vars may add text
        self.timeout = endpoint.get('max_seconds', 60)
        self.vars = self.prepare_vars(text, pre, post, kwargs)
        self.data = self.prepare_data()
        self.query = self.prepare_query()
        self.conn = self.prepare_conn()

    def prepare_vars(self, text, pre, post, kwargs):
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
        vars_ = {
            "text": text,
            "pre": pre,
            "post": post,
        }
        vars_.update(kwargs)
        # expand vars as defined by prompt/vars
        prompt_vars = self.prompt.get('vars', {})
        for k, v in prompt_vars.items():
            # for convenience, in vars, user may specify
            # each line as a string of an array
            if isinstance(v, list):
                v = '\n'.join(v)
            prompt_vars[k] = sublime.expand_variables(v, vars_)
        vars_.update(prompt_vars)
        return vars_

    def prepare_data(self):
        """
        This function prepares data to be sent to an API endpoint.

        Returns:
            data (dict): A dictionary containing the prepared data.
        """
        request = self.endpoint.get('request', {})
        params = self.prompt.get('params', {})
        for k, v in params.items():
            params[k] = sublime.expand_variables(v, self.vars)
        request.update(params)
        data = {}
        valid_params = self.endpoint.get('valid_params', {})
        for k, v in request.items():
            if k in valid_params:  # TODO: check valid_params specified type.
                data[k] = sublime.expand_variables(v, self.vars)
        return data

    def prepare_query(self):
        """
        This function prepares query string to be sent to an API endpoint.

        Returns:
            query (string): A URL encoded string containing the prepared payload.
        """
        query = self.endpoint.get('query', {})
        prompt_query = self.prompt.get('query', {})
        query.update(prompt_query)
        data = {}
        for k, v in query.items():
            data[k] = sublime.expand_variables(v, self.vars)
        return urlencode(data)

    def prepare_conn(self):
        """
        Prepares the HTTP connection based on the endpoint URL.

        Returns:
        http.client.HTTPConnection or http.client.HTTPSConnection: The suitable HTTP connection to be used for
        sending requests to the endpoint URL.
        """
        url = urlparse(self.endpoint.get('url'))
        scheme = url.scheme
        hostname = url.hostname
        port = url.port
        if not url.port:
            port = 443 if scheme == 'https' else 80
        if scheme == 'https':
            # TODO: we should allow connect to servers with custom CA certificates and using client certificates
            return http.client.HTTPSConnection(hostname, port=port)
        return http.client.HTTPConnection(hostname, port=port)

    def run(self):
        self.running = True
        self.result = self.get_response()
        self.running = False

    def get_response(self):
        """
        Pass the given data to remote API, returning the response
        """
        data = json.dumps(self.data)
        method = self.endpoint.get('method', 'POST')
        resource = self.endpoint.get('resource', '')
        resource = str(sublime.expand_variables(resource, self.vars))
        if self.query:
            resource = f"{resource}?{self.query}"
        headers = self.endpoint.get('headers', {})
        self.conn.request(method, resource, data, headers)
        response = self.conn.getresponse()
        return self.parse_response(json.loads(response.read().decode()))

    def parse_response(self, data):
        """
        This function takes in a dictionary 'data' and parses it according to a template defined in 'self.endpoint'.
        It returns a dictionary with keys corresponding to the keys in the template and corresponding values either from the parsed 'data'
        or an error message if any error occurred while parsing
        """
        response = {}
        template = self.endpoint.get('response', {})
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

    def get_item(self, data, path):
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
