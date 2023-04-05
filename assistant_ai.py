import json
import functools
import sublime
import sublime_plugin
from dataclasses import asdict
from typing import Optional

from .assistant_settings import AssistantAISettings, Endpoint, Prompt
from .assistant_thread import AssistantThread

# The global scope ensures that the settings can
# be easily accessed from within all the classes.
settings = AssistantAISettings()
VERSION_ASSISTANT_AI = "1.0.2"
VERSION_ST = int(sublime.version())

def plugin_loaded():
    """
    This module level function is called on ST startup when the API is ready.
    """
    global settings
    settings.load()

def plugin_unloaded():
    """
    This module level function is called just before the plugin is unloaded.
    """
    global settings
    settings.unload()

class AssistantAiTextCommand(sublime_plugin.TextCommand):
    """
    This class represents a Text Command in Sublime Text that with convenient methods.

    Args:
    - sublime_plugin (module): Allows for creating plugins for Sublime Text.

    Methods:
    - get_region_indentation(region): Returns the indentation of a given region.
    - indent_text(text, indent): Indents a given text.
    - get_text_context(region, prompt): Given a region, return the selected text, and context pre and post such text.
    - get_text_context_size(region): returns a dict with the available context parts sizes.
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

    def get_text_context(self, region, prompt: Prompt):
        """
        Returns the text content before and after the region based on the given required context.

        Parameters:
        region (sublime.Region): The region whose context needs to be extracted.
        prompt (dict): The prompt with the required context settings.

        Returns:
        tuple: A tuple containing text, pre and post strings.

        """
        default_rc = {
            "unit": "chars",
            "pre_size": None,
            "post_size": None,
        }
        rc = prompt.required_context if prompt.required_context else default_rc
        text = self.view.substr(region)
        pre = ''
        post = ''
        if rc.get('unit') == 'chars':
            pre_size = rc.get('pre_size')
            if pre_size:
                reg_pre = sublime.Region(region.begin() - pre_size, region.begin())
                pre = self.view.substr(reg_pre)
            post_size = rc.get('post_size')
            if post_size:
                reg_post = sublime.Region(region.end(), region.end() + post_size)
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

    def get_text_context_size(self, region):
        """
        Returns the amount of characters and lines in the text surrounding a given region.

        Args:
            region: A tuple containing two integers indicating the start and end of a region.

        Returns:
            A dictionary with the following keys and values:
                - "pre_chars": The number of characters before the start of the region.
                - "pre_lines": The number of lines before the start of the region.
                - "post_chars": The number of characters after the end of the region.
                - "post_lines": The number of lines after the end of the region.
                - "text_chars": The number of characters within the region.
                - "text_lines": The number of lines within the region.
        """
        region = sublime.Region(*region)
        pre = sublime.Region(0, region.begin())
        post = sublime.Region(region.end(), self.view.size())
        return {
            "pre_chars": len(pre),
            "pre_lines": len(self.view.lines(pre)),
            "post_chars": len(post),
            "post_lines": len(self.view.lines(post)),
            "text_chars": len(region),
            "text_lines": len(self.view.lines(region)),
        }

    def context_to_kwargs(self, **kwargs):
        """
        Takes in keyword arguments and returns those with all non-included context.

        If 'syntax' is not given, it sets the syntax to the view syntax name or an empty string.
        If 'file' is not given, it sets the file to the extracted variables from the view window.
        If 'file_size' is not given, it sets the file size to the view size.
        If 'file_encoding' is not given, it sets the file encoding to the view encoding as a string.
        If 'file_line_endings' is not given, it sets the file line endings to the view line endings as a string.
        If 'file_symbols' is not given, it sets the file symbols to a comma-separated string of the view symbols.
        If 'file_toc' is not given, it sets file_toc to a string of all the view symbols separated by newlines.

        Returns:
        A dictionary of context settings.
        """
        if 'syntax' not in kwargs:
            syntax = self.view.syntax()
            kwargs['syntax'] = syntax.name if syntax else ''
        if 'file' not in kwargs:
            win = self.view.window()
            if win:
                kwargs.update(win.extract_variables())
        if 'file_size' not in kwargs:
            kwargs['file_size'] = str(self.view.size())
        if 'file_encoding' not in kwargs:
            kwargs['file_encoding'] = str(self.view.encoding())
        if 'file_line_endings' not in kwargs:
            kwargs['file_line_endings'] = str(self.view.line_endings())
        if 'file_symbols' not in kwargs:
            syms = [s.strip() for _, s in self.view.symbols()]
            if syms:
                kwargs['file_symbols'] = ', '.join(set(syms))
        if 'file_toc' not in kwargs:
            syms = [s for _, s in self.view.symbols()]
            if syms:
                kwargs['file_toc'] = '\n'.join(syms)
        return kwargs

    def get_region(self):
        """
        Returns a Sublime Region object representing the selected region in the view.
        If several regions are selected, returns the minimum region that covers all selected regions.

        :return: Sublime Region object
        """
        regions = self.view.sel()
        r_start = regions[0].begin()
        r_end = regions[-1].end()
        return sublime.Region(r_start, r_end)

class AssistantAiAsyncCommand(AssistantAiTextCommand):
    global settings

    def handle_thread(self, thread: AssistantThread, seconds=0):
        """
        Recursive method for checking in on the async API fetcher
        """
        timeout = thread.timeout
        icon_warn = "⚠️"
        icon_progress_steps = ["⬜️","◻️","◽️","▫️","◽️","◻️",]
        # If we ran out of time, let user know, stop checking on the thread
        if seconds > timeout:
            msg = f"AssistantAI: {icon_warn} Query ran out of time! {timeout}s"
            sublime.status_message(msg)
            return
        # While the thread is running, show them some feedback,
        # and keep checking on the thread
        if thread.running:
            step = seconds % len(icon_progress_steps)
            progress = icon_progress_steps[step]
            msg = f"AssistantAI is working {progress} - Timout in {timeout-seconds}s"
            sublime.status_message(msg)
            # Wait a second, then check on it again
            sublime.set_timeout(lambda:
                self.handle_thread(thread, seconds + 1), 1000)
            return
        # If we finished with no result, something is wrong
        if not thread.result:
            sublime.status_message(f"AssistantAI: {icon_warn} Something is wrong with remote server - aborting")
            return
        # Collect the result and act as per command spec
        sublime.status_message("AssistantAI: Done!")
        error = thread.result.get('error')
        if error:
            sublime.status_message(f"AsistantAI: {icon_warn} {error}")
            return
        output = thread.result.get('output')
        if not output:
            sublime.status_message(f"AsistantAI: {icon_warn} No response.")
            return
        if isinstance(output, (list, dict)):
            output = json.dumps(output, indent="\t")  # TODO: is this the right think?
        # Get the command to exectue as per prompt specs
        cmds_map = {
            'replace': 'assistant_ai_replace_text',
            'append': 'assistant_ai_append_text',
            'insert': 'assistant_ai_insert_text',
            'output': 'assistant_ai_output_panel',
            'create': 'assistant_ai_create_view',
        }
        prompt_command = thread.prompt.command
        command = cmds_map.get(prompt_command.get('cmd', 'replace'))
        if not command:
            return
        # if the command spec from prompt forces a syntax, take that
        # otherwise, use the prompt var, or 'Markdown'
        if 'syntax' not in prompt_command:
            prompt_command['syntax'] = thread.variables.get('syntax', 'Markdown')
        # run the specified command. kwargs are the params of the command specified in the prompt (if any)
        self.view.run_command(command, {
            "region": [thread.region.begin(), thread.region.end()],
            "text": output,
            "kwargs": prompt_command
        })

    def quick_panel_prompts(self, region, **kwargs):
        """
        Display a quick panel with all available prompts.

        :return: None
        """
        def on_select(index):
            if index < 0:
                return
            pid = ids[index]
            self.view.run_command('assistant_ai_prompt', {"pid": pid, **kwargs})
        # filter prompts by current state
        context_size = self.get_text_context_size(region)
        prompts = settings.prompts
        prompts = settings.filter_prompts_by_syntax(prompts, kwargs.get('syntax'))
        prompts = settings.filter_prompts_by_available_endpoints(prompts)
        prompts = settings.filter_prompts_by_available_context(prompts, context_size)
        ids = []
        items = []
        for pid, prompt in prompts.items():
            ids.append(pid)
            name = sublime.expand_variables(prompt.name, kwargs)
            desc = sublime.expand_variables(prompt.description, kwargs)
            items.append([f"{prompt.icon} {name}", f"{desc} [{pid.upper()}]"])
        if not items:
            icon_warn = "⚠️"
            sublime.status_message(f"AssistantAI: {icon_warn} No available prompts here, in this context.")
            return
        win = self.view.window()
        if win:
            win.show_quick_panel(items=items, on_select=on_select)

    def quick_panel_endpoints(self, **kwargs):
        """
        Display a quick panel with all available endpoints for a given prompt.
        Automatically select the endpoint if only one is available.

        :return: None
        """
        def on_select(index):
            if index < 0:
                return
            eid = ids[index]
            self.view.run_command('assistant_ai_prompt', {
                "eid": eid,
                **kwargs
            })
        pid = kwargs.get('pid')
        if not pid:
            return
        prompt = settings.prompts[pid]
        endpoints = settings.get_endpoints_for_prompt(prompt)
        ids = []
        items = []
        for eid, endpoint in endpoints.items():
            ids.append(eid)
            items.append([f"{endpoint.icon} {endpoint.server_name} {endpoint.name}", f"{endpoint.url} [{eid}]"])
        # for endpoints, if only one choice is available, auto select it
        if not items:
            icon_warn = "⚠️"
            sublime.status_message(f"AssistantAI: {icon_warn} No available endpoints for the selected prompt.")
        if len(items) == 1:
            on_select(0)
            return
        win = self.view.window()
        if not win:
            return
        win.show_quick_panel(items=items, on_select=on_select)

    def quick_panel_list(self, key, items, **kwargs):
        """
        Displays a panel with a list of items to select, and upon selection,
        runs the 'assistant_ai_prompt' command with the selected item, as well as
        additional keyword arguments.

        Returns:
            None
        """
        def on_select(index):
            if index < 0:
                return
            text = items[index]
            self.view.run_command('assistant_ai_prompt', {
                key: text,
                **kwargs
            })
        if not items:
            icon_warn = "⚠️"
            sublime.status_message(f"AssistantAI: {icon_warn} No available items for {key}.")
        if len(items) == 1:
            on_select(0)
            return
        win = self.view.window()
        if not win:
            return
        win.show_quick_panel(items=items, on_select=on_select)

    def input_panel(self, key, caption, **kwargs):
        """
        Displays an input panel to the user with a provided caption and waits for user input to be submitted.

        :return: None
        """
        def on_done(text):
            self.view.run_command('assistant_ai_prompt', {
                key: text,
                **kwargs
            })
        win = self.view.window()
        if not win:
            return
        win.show_input_panel(caption=caption, initial_text="",
            on_done=on_done, on_change=None, on_cancel=None)

class AssistantAiPromptCommand(AssistantAiAsyncCommand):
    global settings

    def run(self, edit, pid: Optional[str]=None, eid: Optional[str]=None, **kwargs):
        prompt: Optional[Prompt] = None
        endpoint: Optional[Endpoint] = None
        # get prompt and endpoint if specificed
        if pid and pid in settings.prompts:
            prompt = settings.prompts[pid]
        if eid and eid in settings.endpoints:
            endpoint = settings.endpoints[eid]
        # ensure that kwargs have basic context
        kwargs = self.context_to_kwargs(**kwargs)
        # ask user for a prompt to use
        if not prompt:
            sublime.set_timeout_async(
                functools.partial(self.quick_panel_prompts, region=self.get_region(), **kwargs))
            return
        # ask the user for the required inputs by the selected prompt
        required_inputs = prompt.required_inputs
        required_inputs = [i.lower() for i in required_inputs if i != 'text']
        for req_in in required_inputs:
            if req_in in kwargs:
                continue  # already solved input
            # follow prompt spects for required inputs (if any is given)
            if prompt.inputs and req_in in prompt.inputs:
                input_spec = prompt.inputs.get(req_in)
                if input_spec and input_spec.input_type == 'list':
                    sublime.set_timeout_async(functools.partial(self.quick_panel_list,
                        key=req_in, items=input_spec.items,
                        pid=pid, eid=eid, **kwargs))
                    return
            # generic input panel
            sublime.set_timeout_async(functools.partial(self.input_panel,
                    key=req_in, caption=req_in.title(),
                    pid=pid, eid=eid, **kwargs))
            return
        # ask user for an endpont to use (if > 1)
        if not endpoint:
            sublime.set_timeout_async(
                functools.partial(self.quick_panel_endpoints, pid=pid, **kwargs))
            return
        # for each selected region, perform a request
        for region in self.view.sel():
            text, pre, post = self.get_text_context(region, prompt)
            if 'text' in required_inputs and len(text) < 1:
                continue
            # TODO: hande_thread is not blocking, so we don't take advantadge of multi selection here.
            # BUG: when user selects multi text, the thread is overwritten. Complex fix ahead!
            thread = AssistantThread(settings, prompt, endpoint, region, text, pre, post, kwargs)
            thread.start()
            self.handle_thread(thread)

class AssistantAiDumpCommand(AssistantAiAsyncCommand):
    global settings

    def run(self, edit):
        data = {
            'endpoints': {k:asdict(v) for k, v in settings.endpoints.items()},
            'prompts': {k:asdict(v) for k, v in settings.prompts.items()},
        }
        self.view.run_command("assistant_ai_create_view", {
            "region": None,
            "text": json.dumps(data, indent="\t"),
            "kwargs": {'syntax': 'JSON'},
        })

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

