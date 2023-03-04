import functools
import sublime
import sublime_plugin

# The global scope ensures that the settings can
# be easily accessed from within all the classes.
from .assistant_settings import AssistantAISettings
from .assistant_thread import AssistantThread

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

class AssistantAiTextCommand(sublime_plugin.TextCommand):
    """
    This class represents a Text Command in Sublime Text that with convenient methods.

    Args:
    - sublime_plugin (module): Allows for creating plugins for Sublime Text.

    Methods:
    - get_region_indentation(region): Returns the indentation of a given region.
    - indent_text(text, indent): Indents a given text.
    - get_context(region, prompt): Given a region, return the selected text, and context pre and post such text.
    """
    def get_region_indentation(self, region):
        """
        Returns the indentation of a region.

        Args:
        - region (tuple): A tuple containing the start and end points of a given region.

        Returns:
        - str: The indentation of the given region.
        """
        lines = self.view.split_by_newlines(sublime.Region(*region))
        if not lines:
            return ''
        text = self.view.substr(sublime.Region(*lines[0]))
        indent = ''
        for c in text:
            if c in (' \t'):
                indent += c
            else:
                break
        return indent

    def indent_text(self, text, indent):
        """
        This function takes in a string and an integer and returns a modified string.
        The string is split by the newline character and every line is then indented by
        the amount specified in the integer. The modified string is then returned.
        """
        new = ''
        for line in text.split('\n'):
            new += indent + line + "\n"
        return new

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

class AssistantAiCommand(AssistantAiTextCommand):
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
            self.view.set_status(error)
        if output:
            command = thread.prompt.get('command', {'cmd':'replace'})
            if isinstance(command, str):
                command = {'cmd': command}
            # if the command spec from prompt forces a syntax, take that
            # otherwise, use the prompt var, or 'Markdown'
            if 'syntax' not in command:
                command['syntax'] = thread.vars.get('syntax', 'Markdown')
            #
            cmds_map = {
                'replace': 'assistant_ai_replace_text',
                'append': 'assistant_ai_append_text',
                'insert': 'assistant_ai_insert_text',
                'output': 'assistant_ai_output_panel',
                'create': 'assistant_ai_create_view',
            }
            cmd = cmds_map.get(command.get('cmd', 'replace'))
            if cmd:
                self.view.run_command(cmd, {
                    "region": [thread.region.begin(), thread.region.end()],
                    "text": output,
                    "kwargs": command
                })

    def quick_panel_prompts(self, syntax=None):
        """
        Display a quick panel with all available prompts.
        """
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
        """
        Display a quick panel with all available endpoints for a given prompt.
        Automatically select the endpoint if only one is available.
        """
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

    # TODO: should accept req_in, caption, and list of options
    def input_panel(self, key, caption, prompt, endpoint, **kwargs):
        """
        Display a input panel asking the user for the instruction.
        """
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

class AssistantAiPromptCommand(AssistantAiCommand):
    global settings

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
                # TODO: seatch an input spec in the prompt to configure the input panel
                sublime.set_timeout_async(functools.partial(self.input_panel,
                        key=req_in, caption=req_in.title(), prompt=prompt,
                        endpoint=endpoint, **kwargs))
                return
        # for each selected region, perform a request
        for region in self.view.sel():
            text, pre, post = self.get_context(region, prompt)
            if len(text) < 1:
                continue
            # TODO: hande_thread is not blocking, so we don't take advantadge of multi selection here.
            # BUG: when user selects multi text, the thread is overwritten. Complex fix ahead!
            thread = AssistantThread(settings, prompt, endpoint, region, text, pre, post, syntax, kwargs)
            thread.start()
            self.handle_thread(thread)

class AssistantAiReplaceTextCommand(AssistantAiTextCommand):
    def run(self, edit, region, text, kwargs):
        """
        Replace the text of a region in a Sublime Text view.

        Parameters:
        edit (Object) : An edit object created to track changes in the view.
        region (tuple) : A tuple containing (start, end) positions of the region to be replaced.
        text (str) : The new text to replace into the region.
        kwargs (dict) : Optional keyword arguments to customize the replacement process:
            - strip_output (bool): Whether or not to remove leading/trailing white space from the new text.
            - new_line_before (bool): Whether or not to add a new line before the new text.
            - new_line_after (bool): Whether or not to add a new line after the new text.
            - preserve_indentation (bool): Whether or not to preserve the indentation of the region after replacement.

        Returns:
        None.
        """
        if kwargs.get('strip_output', True):
            text = text.strip()
        if kwargs.get('new_line_before', False):
            text = "\n" + text
        if kwargs.get('new_line_after', False):
            text = text + "\n"
        if kwargs.get('preserve_indentation', True):
            indent = self.get_region_indentation(region)
            text = self.indent_text(text, indent)
        region = sublime.Region(*region)
        self.view.replace(edit, region, text)

class AssistantAiAppendTextCommand(AssistantAiTextCommand):
    def run(self, edit, region, text, kwargs):
        """
        Inserts `text` into the current view at the end of `region`.

        Args:
        - edit (sublime.Edit): The edit token representing this modification.
        - region (tuple): A tuple containing two integers that represents a region of text in the view.
        - text (str): The text to insert.
        - kwargs (dict): A dictionary that contains the options for text insertion.

        Returns:
        - None

        Options:
        - strip_output (bool, default=True): Whether to strip leading/trailing whitespace from `text`.
        - new_line_before (bool, default=True): Whether to insert a new line before `text`.
        - new_line_after (bool, default=True): Whether to insert a new line after `text`.
        - preserve_indentation (bool, default=True): Whether to preserve the indentation of `region`.

        """
        if kwargs.get('strip_output', True):
            text = text.strip()
        if kwargs.get('new_line_before', True):
            text = "\n" + text
        if kwargs.get('new_line_after', True):
            text = text + "\n"
        if kwargs.get('preserve_indentation', True):
            indent = self.get_region_indentation(region)
            text = self.indent_text(text, indent)
        region = sublime.Region(*region)
        self.view.insert(edit, region.end(), text)

class AssistantAiInsertTextCommand(AssistantAiTextCommand):
    def run(self, edit, region, text, kwargs):
        """
        Replaces a given placeholder with the given text within the specified region.

        Args:
        - edit: a reference to the edit object from Sublime Text.
        - region: the region of text where the placeholder will be replaced.
        - text: the text that replaces the placeholder.
        - kwargs: a dictionary of keyword arguments that can contain 'strip_output' and 'placeholder' keys.

        Returns:
        - None

        """
        if kwargs.get('strip_output', True):
            text = text.strip()
        region = sublime.Region(*region)
        placeholder = kwargs.get('placeholder', 'XXX')
        match = self.view.find(placeholder, region.begin())
        if region.contains(match.begin()) and region.contains(match.end()):
            self.view.replace(edit, match, text)

class AssistantAiOutputPanelCommand(AssistantAiTextCommand):
    def run(self, edit, region, text, kwargs):
        """
        Display output text in a new output panel.

        Params:
        - edit: The sublime edit object.
        - region: The region object.
        - text: The text to display.
        - kwargs: The optional arguments with 2 keys:
                * strip_output: A boolean which determines whether or not to strip the trailing or leading white spaces.
                * syntax: A string which determines the syntax of the text, defaulting to Markdown.
        """
        if kwargs.get('strip_output', True):
            text = text.strip()
        syntax = kwargs.get('syntax', 'Markdown')
        name = 'assistant_ai'
        self.output_panel = self.view.window().create_output_panel(name)
        syntax_list = sublime.find_syntax_by_name(syntax)
        if len(syntax_list) > 0:
            self.output_panel.assign_syntax(syntax_list[0])
        self.view.window().run_command("show_panel", {"panel": f"output.{name}"})
        self.output_panel.run_command('append', {'characters': text})

class AssistantAiCreateViewCommand(AssistantAiTextCommand):
    def run(self, edit, region, text, kwargs):
        """
        Create a new view and assign the appropriate syntax to it. Add the output provided to the new view.

        Parameters:
        edit: This is a required argument that specifies an Edit object that represents a sequence of operations that can be
        applied to the buffer of the text view.

        region: This argument specifies the selected region in the current view. This value is not used in this function.

        text: This argument contains the output text that needs to be added to the newly created view.

        kwargs: This is a dictionary argument that may contain optional parameters for this function. The following parameters
        are supported:

            strip_output: (bool) If `True`, the output text will be stripped of any leading and trailing whitespace before it
            is added to the new view. The default value is `True`.

            syntax: (str) This argument specifies the syntax highlighting to be used for the new view. The default value
            is `'Markdown'`.
        """
        if kwargs.get('strip_output', True):
            text = text.strip()
        syntax = kwargs.get('syntax', 'Markdown')
        # Create a new view
        new_view = self.view.window().new_file()
        # set a proper syntax
        syntax_list = sublime.find_syntax_by_name(syntax)
        if len(syntax_list) > 0:
            new_view.assign_syntax(syntax_list[0])
        # add the output
        new_view.run_command("append", {"characters": text})

