import json
import threading
import functools
import http.client
from urllib.parse import urlparse
import sublime
import sublime_plugin

# The global scope ensures that the settings can
# be easily accessed from within all the classes.
from .settings import AssistantAISettings
settings = AssistantAISettings()
VERSION_ASSISTANT_AI = "0.0.1"
VERSION_ST = int(sublime.version())

def plugin_loaded():
    """
    This module level function is called on ST startup when the API is ready.
    """
    global settings
    settings.load()
    settings.config.add_on_change('assistant_ai', settings.load)

def plugin_unloaded():
    """
    This module level function is called just before the plugin is unloaded.
    """
    global settings
    settings.config.clear_on_change('assistant_ai')

class AssistantAiCommand(sublime_plugin.TextCommand):
    global settings

    def handle_thread(self, thread, seconds=0):
        """
        Recursive method for checking in on the async API fetcher
        """
        max_seconds = settings.get('max_seconds', 60)

        # If we ran out of time, let user know, stop checking on the thread
        if seconds > max_seconds:
            msg = f"Query ran out of time! {max_seconds}s"
            sublime.status_message(msg)
            return

        # While the thread is running, show them some feedback,
        # and keep checking on the thread
        if thread.running:
            msg = "Querying remote AI server, one moment... ({}/{}s)".format(
                seconds, max_seconds)
            sublime.status_message(msg)
            # Wait a second, then check on it again
            sublime.set_timeout(lambda:
                self.handle_thread(thread, seconds + 1), 1000)
            return

        # If we finished with no result, something is wrong
        if not thread.result:
            sublime.status_message("Something is wrong with remote server - aborting")
            return

        error = thread.result.get('error')
        output = thread.result.get('output')
        if error:
            print(error)
        if output:
            # TODO: honor prompt command to run
            self.view.run_command('assistant_ai_replace_text', {
                "region": [thread.region.begin(), thread.region.end()],
                "text": output
            })
        print('------------------')
        print(thread.result.get('response'))
        print('------------------')
        print(output)
        print('------------------')


    def get_avialble_context(self, region):
        # TODO: return num lines and chars for pre of 0 and post of -1 in all regions
        for region in self.view.sel():
            ...

        return {}

    def get_context(self, region, prompt):
        """
        Given a region, return the selected text, and context pre and post such text
        """
        default_required_context = {
            "unit": "chars",
            "pre_size": None,
            "post_size": None,
        }
        rc = prompt.get('required_context', default_required_context)
        text = self.view.substr(region)
        pre = ''
        post = ''
        if rc.get('unit') == 'chars':
            pre_size = rc.get('pre_size')
            if pre_size:
                reg_pre = sublime.Region(region.begin() - pre_size, region.begin())
                # reg_pre = self.view.expand_by_class(reg_pre, sublime.CLASS_LINE_START)
                pre = self.view.substr(reg_pre)
            post_size = rc.get('post_size')
            if post_size:
                reg_post = sublime.Region(region.end(), region.end() + post_size)
                # reg_post = self.view.expand_by_class(reg_post, sublime.CLASS_LINE_END)
                post = self.view.substr(reg_post)
        elif rc.get('unit') == 'lines':
            pre_size = rc.get('pre_size')
            post_size = rc.get('post_size')
            vsize = self.view.size()
            lines = self.view.lines(sublime.Region(0, vsize))
            line_start = self.view.rowcol(region.begin())[0]
            line_end = self.view.rowcol(region.end())[0]
            if pre_size:
                lstart, _ = lines[max(0, line_start - pre_size)]
                _, lend = lines[max(0, line_start - 1)]
                reg_pre = sublime.Region(lstart, lend)
                pre = self.view.substr(reg_pre)
            if post_size:
                lstart, _ = lines[min(line_end + 1, vsize)]
                _, lend = lines[min(line_end + post_size, vsize)]
                reg_post = sublime.Region(lstart, lend)
                post = self.view.substr(reg_post)
        return text, pre, post

class AssistantAiPromptCommand(AssistantAiCommand):
    global settings

    def quick_panel_prompts(self, syntax=None):
        """Display a quick panel with all available prompts."""
        def on_select(index):
            if index < 0:
                return
            pid = ids[index]
            prompt = prompts[pid]
            self.view.run_command('assistant_ai_prompt', {
                "prompt": prompt
            })
        prompts = settings.get_prompts_by_syntax(syntax)
        # TODO: filter by get_prompts_by_available_context
        icon = "♡"
        ids = []
        items = []
        for p, prompt in prompts.items():
            name = prompt.get('name', prompt.get('id', '').replace('_', ' ').title())
            name = sublime.expand_variables(name, {'syntax': syntax})
            desc = prompt.get('description', '')
            desc = sublime.expand_variables(desc, {'syntax': syntax})
            ids.append(p)
            items.append([f"{icon} {name}", f"{desc} [{p.upper()}]"])
        win = self.view.window()
        if win:
            win.show_quick_panel(items=items, on_select=on_select)

    def quick_panel_endpoints(self, prompt):
        """Display a quick panel with all available prompts."""
        def on_select(index):
            if index < 0:
                return
            eid = ids[index]
            endpoint = endpoints[eid]
            self.view.run_command('assistant_ai_prompt', {
                "prompt": prompt,
                "endpoint": endpoint,
            })
        endpoints = settings.get_endpoints_for_prompt(prompt)
        icon = "♢"
        ids = []
        items = []
        for e, endpoint in endpoints.items():
            name = endpoint.get('name', endpoint.get('id', '').replace('_', ' ').title())
            name_server = endpoint.get('name_server', '')
            url = endpoint.get('url', '')
            ids.append(e)
            items.append([f"{icon} {name_server} {name}", f"{url} [{e}]"])
        # for endpoints, if only one choice is available, auto select it
        if len(items) == 1:
            on_select(0)
        else:
            win = self.view.window()
            if win:
                win.show_quick_panel(items=items, on_select=on_select)

    def input_panel(self, key, caption, prompt, endpoint, **kwargs):
        """Display a input panel asking the user for the instruction."""
        # TODO: should accept req_in, caption, and list of options
        def on_done(text):
            self.view.run_command('assistant_ai_prompt', {
                "prompt": prompt,
                "endpoint": endpoint,
                key: text,
                **kwargs
            })
        win = self.view.window()
        if win:
            win.show_input_panel(caption=caption, initial_text="",
                on_done=on_done, on_change=None, on_cancel=None)

    def run(self, edit, prompt=None, endpoint=None, **kwargs):
        # get the syntax
        syntax = self.view.syntax()
        syntax = syntax.name if syntax else None
        # ask user for a prompt to use
        if not prompt:
            sublime.set_timeout_async(
                functools.partial(self.quick_panel_prompts, syntax=syntax))
            return
        # ask user for an endpont to use (if > 1)
        if not endpoint:
            sublime.set_timeout_async(
                functools.partial(self.quick_panel_endpoints, prompt=prompt))
            return
        # ask the user for the required inputs
        required_inputs = prompt.get('required_inputs', [])
        required_inputs = [i.lower() for i in required_inputs if i != 'text']
        for req_in in required_inputs:
            if req_in not in kwargs:
                sublime.set_timeout_async(functools.partial(self.input_panel,
                        key=req_in, caption=req_in.title(), prompt=prompt,
                        endpoint=endpoint, **kwargs))
                return
        # for each selected region, perform a request
        for region in self.view.sel():
            text, pre, post = self.get_context(region, prompt)
            if len(text) < 1:
                continue
            thread = AsyncAssistant(prompt, endpoint, region, text, pre, post, syntax, kwargs)
            thread.start()
            # TODO: hande_thread is blocking, so we don't take advantadge of threading here
            self.handle_thread(thread)

class AsyncAssistant(threading.Thread):
    """
    An async thread class for accessing the remote server API, and waiting for a response
    """
    global settings
    running = False
    result = None

    def __init__(self, prompt, endpoint, region, text, pre, post, syntax, kwargs):
        super().__init__()
        self.endpoint = endpoint
        self.prompt = prompt
        self.region = region
        # prompt vars may add text
        self.vars = self.prepare_vars(text, pre, post, syntax, kwargs)
        self.headers = self.prepare_headers()
        self.data = self.prepare_data()
        self.conn = self.prepare_conn()

    def prepare_vars(self, text, pre, post, syntax, kwargs):
        """
        Prepares variables to be used in a prompt.

        Args:
            text (str): The text to be displayed in the prompt.
            pre (str): The pre-text before text.
            post (str): The post-text after text.
            syntax (str): The syntax of text.
            kwargs (dict): Any additional keyword arguments to be used.

        Returns:
            dict: The updated dictionary of variables.
        """
        prompt_vars = self.prompt.get('vars', {})
        vars_ = {
            "text": text,
            "pre": pre,
            "post": post,
            "syntax": syntax,
            **kwargs
        }
        for k, v in prompt_vars.items():
            prompt_vars[k] = sublime.expand_variables(v, vars_)
        vars_.update(prompt_vars)
        return vars_

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
            return http.client.HTTPSConnection(hostname, port=port)
        return http.client.HTTPConnection(hostname, port=port)

    def prepare_headers(self):
        template = self.endpoint.get('headers', {})
        credentials = settings.credentials
        headers = {}
        for k, v in template.items():
            headers[k] = sublime.expand_variables(v, credentials)
        return headers

    def prepare_data(self):
        request = self.endpoint.get('request', {})
        params = self.prompt.get('params', {})
        for k, v in params.items():
            params[k] = sublime.expand_variables(v, self.vars)
        request.update(params)

        data = {}
        valid_params = self.endpoint.get('valid_params', {})
        for k, v in request.items():
            if k in valid_params:  # TODO: valid params specifies type. We don't check yet.
                data[k] = sublime.expand_variables(v, self.vars)
        return data

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
        # print(method)
        # print(resource)
        # print(self.headers)
        print(data)
        self.conn.request(method, resource, data, self.headers)
        response = self.conn.getresponse()
        return self.parse_response(json.loads(response.read().decode()))

    def parse_response(self, data):
        """
        This function takes in a dictionary 'data' and parses it according to a template defined in 'self.endpoint'.
        It returns a dictionary with keys corresponding to the keys in the template and corresponding values either from the parsed 'data'
        or an error message if any error occurred while parsing
        """
        template = self.endpoint.get('response', {})
        response = {}
        for k, path in template.items():
            item = self.get_item(data, str(path))
            if not item:
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

class AssistantAiReplaceTextCommand(sublime_plugin.TextCommand):
    """
    Simple command for inserting text
    https://forum.sublimetext.com/t/solved-st3-edit-object-outside-run-method-has-return-how-to/19011/7
    """
    def run(self, edit, region, text):
        region = sublime.Region(*region)
        self.view.replace(edit, region, text)
