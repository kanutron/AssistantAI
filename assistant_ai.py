import json
import threading
import http.client
import sublime
import sublime_plugin

VERSION_ASSISTANT_AI = "0.0.1"
VERSION_ST = int(sublime.version())

# The global scope ensures that the settings can
# be easily accessed from within all the classes.
plugin_settings = None

def plugin_loaded():
    """
    This module level function is called on ST startup when the API is ready.
    """
    global plugin_settings
    plugin_settings = AssistantSettings()
    plugin_settings.load()
    # TODO: this is hardcore
    for k in ('credentials', 'prompts', 'servers'):
        plugin_settings.config.add_on_change(k, plugin_settings.load)

def plugin_unloaded():
    """
    This module level function is called just before the plugin is unloaded.
    """
    global plugin_settings
    # TODO: this is hardcore
    if isinstance(plugin_settings, AssistantSettings):
        for k in ('credentials', 'prompts', 'servers'):
            plugin_settings.config.clear_on_change(k)

class AssistantSettings:
    """
    Handles all the settings.
    """
    def __init__(self):
        SETTINGS_FILE = 'assistant_ai.sublime-settings'
        self.config = sublime.load_settings(SETTINGS_FILE)

    def load(self):
        SETTINGS_FILE = 'assistant_ai.sublime-settings'
        self.config = sublime.load_settings(SETTINGS_FILE)
        self.credentials = self.config.get('credentials', {})
        self.servers = self.get_enabled_servers()
        self.prompts = self.get_usable_prompts()

        for s in self.servers:
            print(f"Server: {s}")
        for p in self.prompts:
            print(f"Prompt: {p}")

    def get_enabled_servers(self):
        """
        Returns all configured servers with valid credentials or those don't require any credential
        """
        servers_user = self.get('servers', {})
        servers_def = self.get('servers_default', {})
        servers_all = self.merge_dicts(servers_def, servers_user)
        servers = {}
        servers_to_dismiss = []
        for server_id, server in servers_all.items():
            if not 'requires_credentials' in server:
                servers[server_id] = server  # this server requires no credentials
            if isinstance(server['requires_credentials'], str):
                server['requires_credentials'] = [server['requires_credentials'],]
            for req_cred in server['requires_credentials']:
                if req_cred not in self.credentials:
                    servers_to_dismiss.append(server_id)
            if server_id not in servers_to_dismiss:
                servers[server_id] = server
        return servers

    def get_usable_prompts(self):
        """
        Returns all configured prompts that requires valid available endpoints or no specific endpoints
        """
        prompts_user = self.config.get('prompts', {})
        prompts_def = self.config.get('prompts_default', {})
        prompts_all = self.merge_dicts(prompts_def, prompts_user)
        prompts = {}
        for prompt_id, prompt in prompts_all.items():
            if not 'endpoints' in prompt:
                prompts[prompt_id] = prompt
            if isinstance(prompt['endpoints'], str):
                prompt['endpoints'] = [prompt['endpoints'],]
            for req_srvep in prompt['endpoints']:
                try:
                    srv, ep = req_srvep.split('/', 1)
                    if srv in self.servers and ep in self.servers[srv].get('endpoints', {}):
                        prompts[prompt_id] = prompt
                except Exception:
                    print(f"Error parsing endpoints for prompt {prompt_id}. Should be 'server/endpoint', but got '{req_srvep}'.")
        return prompts

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def merge_dicts(self, old: dict, new: dict) -> dict:
        for k, v in old.items():
            if k in new:
                v.update(new[k])
            new[k] = v
        return new

class AssistantAiCommand(sublime_plugin.TextCommand):
    global plugin_settings
    # settings = plugin_settings

    def check_setup(self):
        """
        Perform a few checks to make sure codex can run
        """
        if len(self.plugin_settings.servers) == 0 or len(self.plugin_settings.prompts) == 0:
            msg = "Please add at least one server's credentials in AssistantAI package settings"
            sublime.status_message(msg)
            raise ValueError(msg)
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
        max_seconds = self.settings.get('max_seconds', 60)

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
        context_sixe = self.settings.get('context_sixe', 512)
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

class AssistantAiEditCommand(AssistantAiCommand):
    def input(self, args):
        if 'server' not in args:
            return ServerListInputHandler()
        elif 'endpoint' not in args:
            return EndpointListInputHandler()
        elif 'prompt' not in args:
            return PromptListInputHandler()
        elif 'instruction' not in args:
            return InstructionInputHandler()

    def run(self, edit, server, endpoint, prompt, instruction):
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

class ServerListInputHandler(sublime_plugin.ListInputHandler):
    def name(self):
        return "server"

    def placeholder(self):
        return "Select a server"

    def description(self, value, text):
        return value.title().replace('_', ' ')

    def list_items(self):
        return [("OpenAI", "openai")]

    def next_input(self, args):
        print(f"ServerInput args: {args}")
        return EndpointListInputHandler()

class EndpointListInputHandler(sublime_plugin.ListInputHandler):
    def name(self):
        return "endpoint"

    def placeholder(self):
        return "Select an endpoint"

    def description(self, value, text):
        return value.title().replace('_', ' ')

    def list_items(self):
        return [("Completions", "completions"), ("Edits", "edits")]

    def next_input(self, args):
        print(f"Endpoint args: {args}")
        return PromptListInputHandler()

class PromptListInputHandler(sublime_plugin.ListInputHandler):
    def name(self):
        return "prompt"

    def placeholder(self):
        return "Select a prompt"

    def description(self, value, text):
        return value.title().replace('_', ' ')

    def list_items(self):
        return [("Python Docstring reST", "python_docstring")]

    def next_input(self, args):
        print(f"PromptInput args: {args}")
        return InstructionInputHandler()

class InstructionInputHandler(sublime_plugin.TextInputHandler):
    def name(self):
        return "instruction"

    def placeholder(self):
        return "Instruction: i.e: 'translate to java' or 'add documentation'"

    def preview(self, text):
        # TODO: preview the rendered prompt
        ...

class AssistantAiReplaceTextCommand(sublime_plugin.TextCommand):
    """
    Simple command for inserting text
    https://forum.sublimetext.com/t/solved-st3-edit-object-outside-run-method-has-return-how-to/19011/7
    """
    def run(self, edit, region, text):
        region = sublime.Region(*region)
        self.view.replace(edit, region, text)
