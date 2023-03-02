import json
import threading
import functools
import http.client
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

    def check_setup(self):
        """
        Perform a few checks to make sure codex can run
        """
        # TODO: these checks are too late if invoked in run()
        if len(settings.servers) == 0 or len(settings.prompts) == 0:
            msg = "Please add at least one server's credentials in AssistantAI package settings"
            sublime.status_message(msg)
            raise ValueError(msg)
        # check selection is valid
        empty = True
        for region in self.view.sel():
            empty = region.empty()
        if empty:
            msg = "Please highlight one or more sections of code."
            sublime.status_message(msg)
            raise ValueError(msg)

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
            # TODO: clean up or delete thread
            return

        # TODO: honor prompt command to run
        self.view.run_command('assistant_ai_replace_text', {
            "region": [thread.region.begin(), thread.region.end()],
            "text": thread.result  # TODO: extract the result text from this response object
        })

    def get_text(self, region):
        """
        Given a region, return the selected text, and context pre and post such text
        """
        # TODO: make pre and post contains only full lines
        context_sixe = settings.get('context_sixe', 512)
        text = self.view.substr(region)
        # get the lines for the context
        lines = self.view.lines(region)
        lstart, _ = lines[0]
        _, lend = lines[-1]
        # get the regions for the context
        reg_pre = sublime.Region(lstart - context_sixe, lstart - 2)
        reg_post = sublime.Region(lend + 3, lend + context_sixe)
        # ensure pre starts in line_start and post ends  in line_end
        reg_pre = self.view.expand_by_class(reg_pre, sublime.CLASS_LINE_START)
        reg_post = self.view.expand_by_class(reg_post, sublime.CLASS_LINE_END)
        # get the context
        pre = self.view.substr(reg_pre)
        post = self.view.substr(reg_post)
        return text, pre, post

class AssistantAiPromptCommand(AssistantAiCommand):
    global settings

    def input(self, args):
        # no server specified but only one available
        # if 'server' not in args and len(settings.servers) == 1:
        #     for server in settings.servers:
        #         args['server'] = server

        # no endpoint specified but the server has only one
        # if 'server' in args and 'endpoint' not in args:
        #     server = settings.servers[args['server']]
        #     if len(server.get('endpoints', {})) == 1:
        #         for endpoint in server:
        #             args['endpoint'] = endpoint

        # check how many prompts are available for this server/endpoint
        # if 'server' in args and 'endpoint' in args:


        # return ServerListInputHandler(args.get('server'))
        # if 'endpoint' not in args:
        #     return EndpointListInputHandler()
        # if 'prompt' not in args:
        syntax = self.view.syntax()
        syntax = syntax.name if syntax else ''
        return PromptListInputHandler(syntax)
        # if 'instruction' not in args:
        #     return InstructionInputHandler()

    def run(self, edit, prompt, endpoint, instruction=None):
        # Check config and prompt
        self.check_setup()

        for region in self.view.sel():
            text, pre, post = self.get_text(region)
            if len(text) < 1:
                continue
            # get the syntax
            # TODO: this gets the syntax for the view, would be nice to get for the region
            syntax = self.view.syntax()
            syntax = syntax.name if syntax else ''
            # run command in a thread
            # TODO: for multiple regions, we may have multiple threads, bit `thread` will be overwritten
            # thread = AsyncAssistant(server, endpoint, prompt, instruction, region, text, pre, post, syntax)
            # thread.start()
            # self.handle_thread(thread)

class AsyncAssistant(threading.Thread):
    """
    An async thread class for accessing the remote server API, and waiting for a response
    """
    running = False
    result = None

    # TODO: pass syntax, filename, extension, ...
    def __init__(self, server, endpoint, prompt, instruction, region, text, pre, post, syntax):
        super().__init__()
        self.server = server
        self.endpoint = endpoint
        self.prompt = prompt
        self.instruction = instruction
        self.region = region
        self.text = text
        self.pre = pre
        self.post = post
        self.syntax = syntax

    def run(self):
        self.running = True
        self.result = self.get_response()
        self.running = False

    def get_response(self):
        """
        Pass the given data to remote API, returning the response
        """
        settings = sublime.load_settings('codex-ai.sublime-settings')
        conn = http.client.HTTPSConnection('api.openai.com')
        headers = {
            'Authorization': "Bearer " + settings.get('open_ai_key', None),
            'Content-Type': 'application/json'
        }
        data = json.dumps(self.data)
        conn.request('POST', '/v1/' + self.endpoint, data, headers)
        response = conn.getresponse()
        respone_dict = json.loads(response.read().decode())
        return respone_dict
        # if respone_dict.get('error', None):
        #     raise ValueError(respone_dict['error'])
        # else:
        #     choice = respone_dict.get('choices', [{}])[0]
        #     ai_text = choice['text']
        #     useage = respone_dict['usage']['total_tokens']
        #     sublime.status_message("Codex tokens used: " + str(useage))
        # return ai_text

# class ServerListInputHandler(sublime_plugin.ListInputHandler):
#     global settings

#     def __init__(self, initial_text):
#         super().__init__()
#         self._initial_text = initial_text

#     def name(self):
#         return "server"

#     def placeholder(self):
#         return "Select a server"

#     def list_items(self):
#         items = []
#         for sid, server in settings.servers.items():
#             items.append((server.get('name', sid.title()), sid))
#         return items

#     def description(self, value, text):
#         return text

#     def next_input(self, args):
#         print(f"Server args: {args}")
#         return EndpointListInputHandler()

class PromptListInputHandler(sublime_plugin.ListInputHandler):
    global settings

    def __init__(self, syntax):
        super().__init__()
        self.syntax = syntax.lower()

    def name(self):
        return "prompt"

    def placeholder(self):
        return "Select a prompt"

    def description(self, value, text):
        return text

    def list_items(self):
        items = []
        for pid, prompt in settings.prompts.items():
            if self.syntax in prompt.get('required_syntax', [self.syntax,]):
                items.append((prompt.get('name', pid.title()), pid))
        return items

    def next_input(self, args):
        # if 'prompt' not in args:
        #     return PromptListInputHandler(self.syntax)
        prompt = settings.prompts[args['prompt']]
        print(f"PromptInput args: {args}") # DEBUG
        if 'instruction' in prompt.get('required_inputs', []):
            return InstructionInputHandler()
        else:
            args.setdefault('instruction', '')
            return EndpointListInputHandler()


class InstructionInputHandler(sublime_plugin.TextInputHandler):
    def name(self):
        return "instruction"

    def placeholder(self):
        return "Instruction: i.e: 'translate to java' or 'add documentation'"

    def preview(self, text):
        # TODO: preview the rendered prompt
        ...

    def next_input(self, args):
        prompt = settings.prompts.get(args.get('prompt', ''))
        # if not prompt:
        #     return PromptListInputHandler('')
        req_ep = prompt.get('required_endpoints', [])
        if req_ep and len(req_ep) <= 1:
            args.setdefault('endpoint', prompt['required_endpoints'][0])
            print(f"InstructionInput args: {args}") # DEBUG
        else:
            print(f"InstructionInput args: {args}") # DEBUG
            return EndpointListInputHandler()

class EndpointListInputHandler(sublime_plugin.ListInputHandler):
    global settings

    def name(self):
        return "endpoint"

    def placeholder(self):
        return "Select an endpoint"

    def list_items(self):
        items = []
        for eid, endpoint in settings.endpoints.items():
            items.append((endpoint.get('name', eid.title()), eid))
        return items

    def description(self, value, text):
        return text

    def next_input(self, args):
        print(f"EndpointInput args: {args}") # DEBUG
        args.setdefault('instruction', '')

class AssistantAiReplaceTextCommand(sublime_plugin.TextCommand):
    """
    Simple command for inserting text
    https://forum.sublimetext.com/t/solved-st3-edit-object-outside-run-method-has-return-how-to/19011/7
    """
    def run(self, edit, region, text):
        region = sublime.Region(*region)
        self.view.replace(edit, region, text)
