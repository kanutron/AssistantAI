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

        # TODO: make this configurable
        ai_text = ''
        if thread.result.get('error', None):
            raise ValueError(thread.result['error'])
        else:
            choice = thread.result.get('choices', [{}])[0]
            ai_text = choice['text']
            useage = thread.result['usage']['total_tokens']
            sublime.status_message("Codex tokens used: " + str(useage))

        # TODO: honor prompt command to run
        self.view.run_command('assistant_ai_replace_text', {
            "region": [thread.region.begin(), thread.region.end()],
            "text": ai_text  # TODO: extract the result text from this response object
        })


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
        # TODO: filter by get_prompts_by_context
        icon = "♡"
        ids = []
        items = []
        for p, prompt in prompts.items():
            name = prompt.get('name', prompt.get('id', '').replace('_', ' ').title())
            desc = prompt.get('description', '')
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
        prompt_vars = self.prompt.get('provided_vars', {})
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
        params = self.endpoint.get('params', {})
        valid_params = self.endpoint.get('valid_params', {})
        prompt_params = self.prompt.get('provided_params', {})
        for k, v in prompt_params.items():
            prompt_params[k] = sublime.expand_variables(v, self.vars)
        params.update(prompt_params)
        data = {}
        for k, v in params.items():
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
        print(method)
        print(resource)
        print(self.headers)
        print(data)
        self.conn.request(method, resource, data, self.headers)
        response = self.conn.getresponse()
        respone_data = json.loads(response.read().decode())
        return respone_data

class AssistantAiReplaceTextCommand(sublime_plugin.TextCommand):
    """
    Simple command for inserting text
    https://forum.sublimetext.com/t/solved-st3-edit-object-outside-run-method-has-return-how-to/19011/7
    """
    def run(self, edit, region, text):
        region = sublime.Region(*region)
        self.view.replace(edit, region, text)
