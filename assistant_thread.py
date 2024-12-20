import os
import json
import threading
import sublime
import ssl
import http.client
from urllib.parse import urlparse, urlencode
from .assistant_settings import AssistantAISettings, Endpoint, Prompt

class AssistantThread(threading.Thread):
    """
    An async thread class for accessing the remote server API, and waiting for a response
    """
    def __init__(self, settings, prompt, endpoint, region, text, pre, post, stack, kwargs):
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
        for k, v in self.prompt.variables.items():
            # for convenience, in vars, user may specify
            # each line as a string of an array
            if isinstance(v, list):
                v = '\n'.join(v)
            vars_[k] = str(sublime.expand_variables(v, vars_))
        return vars_

    def prepare_data(self):
        """
        This function prepares data to be sent to an API endpoint.

        Returns:
            data (dict): A dictionary containing the prepared data.
        """
        request = {}
        request.update(self.endpoint.request)
        request.update(self.prompt.params)
        for k, v in request.items():
            request[k] = sublime.expand_variables(v, self.variables)
        to_filter = set()
        for k, v in request.items():
            if k not in self.endpoint.valid_params:
                to_filter.add(k)
                print("AssistantAI: WARNING: prompt '{}' provides a param '{}' not accepted by endpoint '{}'.".format(
                    self.prompt.pid, k, self.endpoint.eid))
            # TODO: check valid_params specified type.
        return dict((k,v) for k,v in request.items() if k not in to_filter)

    def prepare_query(self):
        """
        This function prepares query string to be sent to an API endpoint.

        Returns:
            query (string): A URL encoded string containing the prepared payload.
        """
        query = {}
        query.update(self.endpoint.query)
        query.update(self.prompt.query)
        data = {}
        for k, v in query.items():
            data[k] = str(sublime.expand_variables(v, self.variables))
        return urlencode(data)

    def prepare_conn(self):
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
            context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            if isinstance(self.endpoint.credentials, dict):
                verify = self.endpoint.credentials.get('verify')
                cert = self.endpoint.credentials.get('cert')
                if verify:
                    verify = str(os.path.expanduser(verify))
                    context.load_verify_locations(cafile=verify)
                    if cert:
                        cert = str(os.path.expanduser(cert))
                        context.load_cert_chain(cert)
            return http.client.HTTPSConnection(hostname, port=port, context=context)
        return http.client.HTTPConnection(hostname, port=port)

    def run(self):
        """
        Sets the 'running' attribute to True, gets a response using the 'get_response' method,
        assigns the response to the 'result' attribute, and sets the 'running' attribute to False.

        Parameters:
        self: An instance of the class.
        """
        try:
            self.running = True
            self.result = self.get_response()
            self.running = False
        except Exception as e:
            self.result = {'error': e}
            print("AssistantAI: Error while processing prompt: {}".format(e))
            self.running = False

    def get_response(self):
        """
        Send a request to the endpoint specified in self.endpoint, with the data
        specified in self.data, and return the parsed JSON response.

        :return: A dictionary containing the response data.
        :rtype: Dict[str, Any]
        """
        data = json.dumps(self.data)
        method = self.endpoint.method
        resource = self.endpoint.resource
        resource = str(sublime.expand_variables(resource, self.variables))
        if self.query:
            resource = "{0}?{1}".format(resource, self.query)
        headers = self.endpoint.headers if self.endpoint.headers else {}
        self.conn.request(method, resource, data, headers)
        response = self.conn.getresponse()
        return self.endpoint.parse_response(json.loads(response.read().decode()))
