import sublime
import copy
import uuid
from dataclasses import dataclass
from typing import Dict, List, Set, Any, Optional, Union
from .assistant_qdict import QDict

PKG_NAME = 'AssistantAI'
SETTINGS_FILE = 'assistant_ai.sublime-settings'
PKG_SETTINGS_FILE_BLOB = 'assistant_ai*.sublime-settings'

# types for hinting
Credentials = Dict[str, Any]

@dataclass
class SettingsDataLoader:
    ident: str
    spec: Dict[str, Any]
    import_spec: Dict[str, Any]
    import_result: Optional[bool]

    def __init__(self, data: dict, ident: Optional[str]=None, item_type: str='item'):
        """
        Loads the item from the given dict coming from Sublime settings.
        If the item imports from another, this is not processed. Call import_from(...).
        """
        # Item identification data
        if not ident:
            ident = item_type + '_' + str(uuid.uuid4())
        self.spec = data
        self.ident = ident
        # Import specifications
        self.import_spec = self.load_dict(data, 'import', str_to_dict='from')
        self.import_result = None

    def load_str(self, data: Union[dict, sublime.Settings], key: str, alt: str='') -> str:
        """
        Load a string value from the given data dictionary using the given key.

        Args:
            data (dict): The dictionary containing the key-value pair.
            key: The key to retrieve the value.
            alt (str): The alternate value to return if key is not found.

        Returns:
            str: The value of the key in data dictionary, or alt if key is not found or value is empty.

        Raises:
            TypeError: If item is not a string.
        """
        if not data:
            return alt
        try:
            item = data.get(key, alt)
        except TypeError:
            return alt
        if not item:
            return alt
        if isinstance(item, str):
            return item
        raise TypeError(f"'{key}' must be a string. id='{self.ident}'.")

    def load_int(self, data: Union[dict, sublime.Settings], key: str, alt: int=0) -> int:
        if not data:
            return alt
        try:
            item = data.get(key, alt)
        except TypeError:
            return alt
        if not item:
            return alt
        if isinstance(item, int):
            return item
        raise TypeError(f"'{key}' must be an integer. id='{self.ident}'.")

    def load_dict(self, data: Union[dict, sublime.Settings], key: str, str_to_dict: Optional[str]=None) -> dict:
        if not data:
            return {}
        try:
            item = copy.deepcopy(data.get(key, {}))
        except TypeError:
            return {}
        if not item:
            return {}
        if str_to_dict and isinstance(item, str) and isinstance(str_to_dict, str):
            item = {str_to_dict: item}
        if not isinstance(item, dict):
            if not str_to_dict:
                raise TypeError(f"'{key}' must be an object. id='{self.ident}'.")
            else:
                raise TypeError(f"'{key}' must be an object or string. id='{self.ident}'.")
        return item

    def load_list_str(self, data: Union[dict, sublime.Settings], key: str, str_to_list: bool=True) -> List[str]:
        if not data:
            return []
        try:
            items = copy.deepcopy(data.get(key, []))
        except TypeError:
            return []
        if not items:
            return []
        if str_to_list and isinstance(items, str):
            items = [items, ]
        if not isinstance(items, list):
            raise TypeError(f"'{key}' must be a list of strings. id='{self.ident}'.")
        for item in items:
            if not isinstance(item, str):
                raise TypeError(f"'{key}' must be a list of strings. id='{self.ident}'.")
        return items

    def load_list_dict(self, data: Union[dict, sublime.Settings], key: str) -> List[dict]:
        if not data:
            return []
        try:
            items = copy.deepcopy(data.get(key, []))
        except TypeError:
            return []
        if not items:
            return []
        if not isinstance(items, list):
            raise TypeError(f"'{key}' must be a list of objects. id='{self.ident}'.")
        for item in items:
            if not isinstance(item, dict):
                raise TypeError(f"'{key}' must be a list of objects. id='{self.ident}'.")
        return items

    def ensure_dict_str_str(self, data:Dict[str, Any], dismiss:bool=True) -> Dict[str, str]:
        if dismiss:
            return {k:v for k,v in data.items() if isinstance(v, str)}
        else:
            return {k:str(v) for k,v in data.items()}

    def import_pending(self) -> bool:
        if not self.import_spec:
            return False
        return self.import_result is None

    def import_done(self) -> bool:
        return self.import_result is True

    def import_failed(self) -> bool:
        return self.import_result is False

    def import_failure(self):
        self.import_result = False
        return self

    def import_completed(self):
        self.import_result = True
        return self

    def import_from(self, parents: Dict[str, Any], chain: Optional[List[str]]=None):
        """
        Process the item import specification given the current available parents
        and return a new expanded Item without the import statement.

        It's called recursively to solve parents that are still pending.

        Chain is used to record the import chain. If the same id is found twice is an indication
        of a cyclic dependency, and the import will fail.
        """
        if not self.import_pending():
            return self
        if not isinstance(chain, list):
            chain = []
        # get intended parent id
        parent_id = self.import_spec.get('from')
        if not isinstance(parent_id, str):
            return self.import_failure()
        # chain check for duplicates = cyclic dependency
        if parent_id in chain:
            return self.import_failure()
        chain.append(parent_id)
        # check if parent exists
        if not parent_id in parents:
            return self.import_failure()
        # check the parent is same type as self
        if not isinstance(parents[parent_id], type(self)):
            return self.import_failure()
        # import parent if needed
        if parents[parent_id].import_pending():
            parents[parent_id] = parents[parent_id].import_from(parents, chain)
            if parents[parent_id].import_failed():
                return self.import_failure()
        # create a new item from parent
        return self.from_parent(parents[parent_id])

    def from_parent(self, parent):
        """
        Given a parent return a new processed Item as per the import specs.

        Parent must not have the import key. That is, if the parent depends on
        another ancestor, that should be resolved first.
        """
        # create a new item specification as if it was specified in settings
        new_spec = copy.deepcopy(parent.spec)
        new_spec.update(self.spec)
        # fine tuning as defined by the user in the 'import' key
        # TODO: generalize this
        actions = {
            'import': 'delete',
            'required_inputs': 'replace',
            'required_syntax': 'update',
            'required_context': 'replace',
            'required_endpoints': 'update',
            'inputs': 'update',
            'vars': 'update',
            'params': 'update',
            'query': 'update',
            'command': 'replace',
        }
        self.import_spec['import'] = 'delete'  # force this to be deleted when importing
        for key, action in actions.items():
            parent_v = parent.spec.get(key)
            prompt_v = self.spec.get(key)
            if not parent_v or not prompt_v:
                continue
            action = self.import_spec.get(key, action)
            if action == 'replace':
                continue
            if action == 'delete':
                del(new_spec[key])
                continue
            # then is update, which depends on the source/target types
            if isinstance(parent_v, list) and isinstance(prompt_v, list):
                new_spec[key] = parent_v + prompt_v
                continue
            if isinstance(parent_v, dict) and isinstance(prompt_v, dict):
                new_spec[key] = copy.deepcopy(parent_v)
                new_spec[key].update(prompt_v)
                continue
        # return a new Item created from the resulting specification
        cls = type(self)
        return cls(new_spec, self.ident).import_completed()

@dataclass
class Endpoint(SettingsDataLoader):
    eid: str
    name: str
    icon: str
    # endpoint interface
    method: str
    resource: str
    # prompt requirements
    required_vars: List[str]
    # request body and params specification
    valid_params: Dict[str, str]
    request: Dict[str, Any]
    query: Dict[str, str]
    # response data retrieval specification
    response: Dict[str, Any]
    # server data
    sid: Optional[str]
    server_name: Optional[str]
    url: Optional[str]
    timeout: Optional[int]
    credentials: Optional[Credentials]
    required_credentials: Optional[List[str]]
    headers: Optional[Dict[str, str]]

    def __init__(self, data: dict, ident: Optional[str]=None, item_type: str='endpoint'):
        """
        Loads the endpoint from the given dict coming from Sublime settings.
        If the endpoint imports from another, this is not processed. Call import_from(...).
        """
        super().__init__(data, ident, item_type)
        # Identification data
        self.eid = self.load_str(data, 'id', self.ident)
        self.name = self.load_str(data, 'name', self.eid.replace('_', ' ').title())
        self.icon = self.load_str(data, 'icon', '↯')
        # Endpoint interface
        self.method = self.load_str(data, 'method', 'POST')
        self.resource = self.load_str(data, 'resource', '')
        # prompt requirements
        self.required_vars = self.load_list_str(data, 'required_vars')
        # request body and params specification
        self.valid_params = self.load_dict(data, 'valid_params')
        self.request = self.load_dict(data, 'request')
        self.query = self.load_dict(data, 'query')
        # response data retrieval specification
        self.response = self.load_dict(data, 'response')
        if 'paths' not in self.response:  # backwards compatibility to simple response definition
            self.response['paths'] = {
                'error': self.response.get('error', 'error'),
                'text': self.response.get('output', 'data'),
            }
            self.response['output'] = "${text}"
            if 'error' in self.response:
                del(self.response['error'])
        # ensure we have paths for text, list error, and vars
        self.response['paths'].setdefault('text', 'data')
        self.response['paths'].setdefault('error', 'error')
        self.response.setdefault('output', "${text}")
        # server data
        self.sid = None
        self.server_name = None
        self.url = None
        self.timeout = None
        self.credentials = None
        self.required_credentials = None
        self.headers = None

    def set_server_data(self, server: 'Server') -> None:
        """
        Set the server data (ID, server name, URL, timeout, credentials, required credentials, and headers)
        Args:
            server (Server): The server object containing the desired data to be set.
        Returns:
            None.
        """
        self.sid = server.sid
        self.server_name = server.name
        self.url = server.url
        self.timeout = server.timeout
        self.credentials = server.credentials
        self.required_credentials = server.required_credentials
        self.headers = server.headers

    def parse_response(self, data: dict) -> Dict[str, Any]:
        response: Dict[str, Any] = {}
        # get the response remplate of the endpoint
        spec = self.response
        paths = spec.get('paths', {})
        output = spec.get('output', '${text}')
        if not spec or not paths or not isinstance(paths, dict):
            response['error'] = f"The endpoint doesn't specify any valid reponse template."
            return response
        # get the data from specified paths
        qdata = QDict(data)
        for key, path in paths.items():
            if '*' in path:
                response[key] = qdata.values(path)
            else:
                response[key] = qdata.get(path)
        # collect all vars from the object retreived with path 'vars'
        if 'vars' in response and isinstance(response['vars'], dict):
            for k, v in response['vars'].items():
                if not isinstance(v, (list, dict)):
                    k = '_' + str(k) if k in response else str(k)
                    response[k] = str(v)
        # expand output, with keys in response and collected vars
        str_response = self.ensure_dict_str_str(response)
        response['output'] = sublime.expand_variables(output, str_response)
        # prepare the returned list (used for inputs of type 'list_from_prompt')
        if 'list' in response and isinstance(response['list'], list):
            new_list = []
            templates = spec.get('templates', {})
            list_item_template = templates.get('list_item')
            if list_item_template:
                for item in response['list']:
                    if isinstance(item, dict):
                        str_item = self.ensure_dict_str_str(item)
                        new_item = sublime.expand_variables(list_item_template, str_item)
                        new_list.append(new_item)
                    else:
                        new_list.append([str(item)])
            else:
                new_list = [[str(item)] for item in response['list']]
            response['list'] = new_list
        # include raw response
        response['response'] = data
        return response

@dataclass
class Server(SettingsDataLoader):
    sid: str
    name: str
    url: str
    timeout: int
    # server requirements
    credentials: Credentials
    required_credentials: List[str]
    # specs
    headers: Dict[str, str]
    endpoints: Dict[str, Endpoint]

    def __init__(self, data: dict, ident: Optional[str]=None, item_type: str='server'):
        """
        Loads the server from the given dict coming from Sublime settings.
        If the server imports from another, this is not processed. Call import_from(...).
        """
        super().__init__(data, ident, item_type)
        # Identification data
        self.sid = self.load_str(data, 'id', self.ident)
        self.name = self.load_str(data, 'name', self.sid.replace('_', ' ').title())
        self.url = self.load_str(data, 'url')
        self.timeout = self.load_int(data, 'timeout')
        # Server requirements
        self.credentials = {}
        self.required_credentials = self.load_list_str(data, 'required_credentials')
        # Server specifications
        self.headers = self.load_dict(data, 'headers')
        # Server endpoints
        self.endpoints = {}
        endpoints = self.load_dict(data, 'endpoints')
        for eid in endpoints:
            self.endpoints[eid] = Endpoint(endpoints[eid], eid)
            self.endpoints[eid].set_server_data(self)

    def set_credentials(self, credentials: Credentials) -> None:
        self.credentials = credentials
        # this loads headers without processing again
        self.headers = self.load_dict(self.spec, 'headers')
        safe_creds = self.ensure_dict_str_str(self.credentials)
        for k, v in self.headers.items():
            self.headers[k] = str(sublime.expand_variables(v, safe_creds))
        for eid in self.endpoints:
            self.endpoints[eid].set_server_data(self)

@dataclass
class PromptInput(SettingsDataLoader):
    name: str
    type: str
    caption: str
    description: str
    items: Optional[List[str]]
    prompt_id: Optional[str]
    prompt_args: Optional[Dict[str, Any]]

    def __init__(self, data: dict, ident: Optional[str]=None, item_type: str='prompt_input'):
        """
        Loads the prompt input from the given dict coming from Sublime settings.
        If type is list, items must be provided.
        """
        super().__init__(data, ident, item_type)
        # Prompt input specification
        self.name = self.ident
        self.type = self.load_str(data, 'type', 'text').lower()
        self.caption = self.load_str(data, 'caption', self.ident.replace('_', ' ').title())
        self.description = self.load_str(data, 'description', self.caption)
        self.items = None
        self.prompt_id = None
        self.prompt_args = None
        if self.type == 'list':
            self.items = self.load_list_str(data, 'items')
        elif self.type == 'text':
            ...
        elif self.type == 'list_from_prompt':
            self.prompt_id = self.load_str(data, 'prompt_id')
            self.prompt_args = self.load_dict(data, 'prompt_args')
        elif self.type == 'text_from_prompt':
            self.prompt_id = self.load_str(data, 'prompt_id')
            self.prompt_args = self.load_dict(data, 'prompt_args')

@dataclass
class Prompt(SettingsDataLoader):
    pid: str
    name: str
    icon: str
    description: str
    # input definitions
    inputs: Dict[str, PromptInput]
    # prompt requirements
    required_inputs: List[str]
    required_syntax: List[str]
    required_context: Dict[str, Any]
    required_endpoints: List[str]
    # variables offered by this prompt
    variables: Dict[str, Any]
    # call payload, query-string and data body
    params: Dict[str, Any]
    query: Dict[str, str]
    # the command to execute once the prompt is processed
    command: Dict[str, Any]

    def __init__(self, data: dict, ident: Optional[str]=None, item_type: str='prompt'):
        """
        Loads the prompt from the given dict coming from Sublime settings.
        If the prompt imports from another, this is not processed. Call import_from(...).
        """
        super().__init__(data, ident, item_type)
        # Prompt identification data
        self.pid = self.load_str(data, 'id', self.ident)
        self.name = self.load_str(data, 'name', self.pid.replace('_', ' ').title())
        self.icon = self.load_str(data, 'icon', '♡')
        self.description = self.load_str(data, 'description', self.name)
        # Input definitions
        self.inputs = {}
        inputs = self.load_dict(data, 'inputs')
        for iid in inputs:
            self.inputs[iid] = PromptInput(inputs[iid], iid)
        # Prompt requirements
        self.required_inputs = self.load_list_str(data, 'required_inputs')
        self.required_syntax = self.load_list_str(data, 'required_syntax')
        self.required_context = self.load_dict(data, 'required_context')
        self.required_endpoints = self.load_list_str(data, 'required_endpoints')
        # Variables
        self.variables = self.load_dict(data, 'vars')
        if not self.variables:
            prompt_vars = {}
            for r in self.required_inputs:
                prompt_vars[r] = f'${{{r}}}'
            self.variables = prompt_vars
        # Payload params and query
        self.params = self.load_dict(data, 'params')
        self.query = self.load_dict(data, 'query')
        # Command to execute
        self.command = self.load_dict(data, 'command', str_to_dict='cmd')

    def get_sublime_command(self):
        cmdmap = {
            'replace': 'assistant_ai_replace_text',
            'append': 'assistant_ai_append_text',
            'insert': 'assistant_ai_insert_text',
            'output': 'assistant_ai_output_panel',
            'create': 'assistant_ai_create_view',
        }
        cmd = self.command.get('cmd', 'replace')
        if not isinstance(cmd, str):
            cmd = 'replace'
        return cmdmap.get(cmd, 'assistant_ai_replace_text')

@dataclass
class AssistantAISettings(SettingsDataLoader):
    """
    Handles all AssistantAI settings.
    """
    prompts: Dict[str, Prompt]
    endpoints: Dict[str, Endpoint]
    settings_callbacks: Dict[str, sublime.Settings]

    def __init__(self):
        super().__init__({}, ident='assistant_ai', item_type='root_settings')
        self.prompts = {}
        self.endpoints = {}
        self.settings_callbacks = {}

    def load(self) -> None:
        """
        Loads settings and prompts from all packages that provides AssistantAI settings.
        Any package providing assistant_ai*.sublime-settings will be processed.

        Each package provided endpoints can only use credentials from its own settings files
        but can rely on other packages configured end points.

        :return: None
        """
        # Get all settings from all packages that provides AssistantAI settings.
        files: Set[str] = set()
        for resource in sublime.find_resources(PKG_SETTINGS_FILE_BLOB):
            files.add(resource.split('/')[-1])
        # load endpoints for each settings file.
        for file in files:
            settings = self.load_settings_from(file)
            credentials = self.load_credentials_from(settings)
            servers = self.load_servers_from(settings, credentials)
            eps = self.load_endpoints_from(servers)
            self.endpoints.update(eps)
        # load prompts now that we have all end points loaded.
        for file in files:
            settings = self.load_settings_from(file)
            prompts = self.load_prompts_from(settings)
            self.prompts.update(prompts)
        # since some prompts may import from others, process the import statements
        for pid, prompt in self.prompts.items():
            self.prompts[pid] = prompt.import_from(self.prompts)

    def unload(self) -> None:
        """
        Clears all the 'assistant_ai' settings on_change callbacks from the
        `settings_callbacks` dictionary.

        :return: None
        """
        for file in self.settings_callbacks:
            self.settings_callbacks[file].clear_on_change('assistant_ai')

    def load_settings_from(self, file: str) -> sublime.Settings:
        """
        Load settings from a given file in Sublime Text.

        Args:
        * file: A string representing the file path of the settings file.

        Returns:
        * settings: The loaded settings from the file.

        Side Effects:
        * Adds a callback for the settings file if it has not been registered before.
        If a change is made to that file, reload will happen.
        """
        settings = sublime.load_settings(file)
        if file not in self.settings_callbacks:
            settings.add_on_change('assistant_ai', self.load)
            self.settings_callbacks[file] = settings
        return settings

    def load_credentials_from(self, settings: sublime.Settings) -> Credentials:
        """
        Extracts valid credentials from settings.

        :param settings: A dictionary containing credentials data.
        :return: A dictionary containing valid credentials.
        """
        creds_all = self.load_dict(settings, 'credentials')
        creds = {}
        for cid, cred in creds_all.items():
            if cred is not None:
                creds[cid] = cred
        return creds

    def get_credentials_for(self, server: Server, credentials: dict) -> Credentials:
        creds = {}
        if server.sid in credentials and isinstance(credentials[server.sid], dict):
            creds.update(credentials[server.sid])
        elif isinstance(credentials, dict):
            creds.update(credentials)
        return {k:v for k,v in creds.items() if isinstance(v, str)}

    def load_servers_from(self, settings: sublime.Settings, credentials: Credentials) -> Dict[str, Server]:
        """
        This function loads available servers from settings and return servers
        that can be accessed using provided credentials.

        :param settings: The settings to be used to load servers.
        :type settings: dict
        :param credentials: The credentials to access servers.
        :type credentials: dict
        :return: A dictionary containing Id and info of servers that can be accessed using provided credentials.
        :rtype: dict
        """
        servers_list: List[dict] = []
        servers_list += self.load_list_dict(settings, 'default_servers')
        servers_list += self.load_list_dict(settings, 'servers')
        # create Server objects and keep only valid ones
        servers: Dict[str, Server] = {}
        for server in servers_list:
            new = Server(server)
            servers[new.sid] = new
        # process imports before anything else
        for sid in servers:
            servers[sid] = servers[sid].import_from(servers)
        # filter to usable ones by available credentials
        to_dismiss = []
        for sid in servers:
            if not servers[sid].required_credentials:
                continue
            # identify servers to be dismissed
            srv_creds = self.get_credentials_for(servers[sid], credentials)
            for req_cred in servers[sid].required_credentials:
                if req_cred not in srv_creds or not srv_creds.get(req_cred):
                    to_dismiss.append(sid)
                    break
            # process server headers
            if sid not in to_dismiss:
                servers[sid].set_credentials(srv_creds)
            else:
                print(f"AssistantAI: Server '{sid}' dismissed due to missing required credentials.")
        return {sid:srv for sid,srv in servers.items() if sid not in to_dismiss}

    def load_endpoints_from(self, servers: Dict[str, Server]) -> Dict[str, Endpoint]:
        """
        Load all available endpoints from given servers and process their headers.

        :param servers: A dictionary containing information about servers.
        :type servers: dict
        :return: A dictionary containing available endpoints with processed headers.
        :rtype: dict
        """
        # all server keys except those banned will be added into endpoint
        endpoints = {}
        for sid, server in servers.items():
            for eid, endpoint in server.endpoints.items():
                endpoints[f'{sid}/{eid}'] = endpoint
        return endpoints

    def load_prompts_from(self, settings: sublime.Settings) -> Dict[str, Prompt]:
        """
        This function loads prompts from the settings file and filters out prompts that require unavailable endpoints.

        Args:
        - settings: dictionary containing all settings

        Returns:
        - prompts: dictionary containing all prompts that were not filtered out
        """
        # load prompt specs from settings
        prompts_list = []
        prompts_list += self.load_list_dict(settings, 'default_prompts')
        prompts_list += self.load_list_dict(settings, 'prompts')
        # create Prompt objects and keep only valid ones
        prompts = {}
        for prompt in prompts_list:
            prompt = Prompt(prompt)
            if not prompt.required_endpoints:
                prompts[prompt.pid] = prompt
                continue
            for ep in prompt.required_endpoints:
                if ep in self.endpoints:
                    prompts[prompt.pid] = prompt
                    break
        return prompts

    # TODO: typing for available context
    def filter_prompts_by_available_context(self, prompts: Dict[str, Prompt], available_context) -> Dict[str, Prompt]:
        """
        Returns all usable prompts filtering by current edit state.
        Selected text, available context pre and/or post contents.
        """
        to_filter = set()
        for p, prompt in prompts.items():
            if 'text' in prompt.required_inputs:
                if available_context.get('text_chars') < 1:
                    to_filter.add(p)
                    continue
            if not prompt.required_context:
                continue
            req_crx = prompt.required_context
            unit = req_crx.get('unit', 'chars')
            req_pre = req_crx.get('pre_size', None)
            req_post = req_crx.get('post_size', None)
            pre = available_context.get('pre_' + unit)
            post = available_context.get('post_' + unit)
            if req_pre and req_pre > pre:
                to_filter.add(p)
            if req_post and req_post > post:
                to_filter.add(p)
        return {k: v for k, v in prompts.items() if k not in to_filter}

    def filter_prompts_by_available_endpoints(self, prompts: Dict[str, Prompt]) -> Dict[str, Prompt]:
        """
        Returns all usable prompts filtering by availability of suitable endpoints.
        Selected text, available context pre and/or post contents.
        """
        to_filter = set()
        for p, prompt in prompts.items():
            eps = self.get_endpoints_for_prompt(prompt)
            if len(eps) < 1:
                to_filter.add(p)
        return {k: v for k, v in prompts.items() if k not in to_filter}

    def filter_prompts_by_syntax(self, prompts: Dict[str, Prompt], syntax: Optional[str]=None) -> Dict[str, Prompt]:
        """
        Returns all loaded usable prompts filtering by syntax
        """
        if not syntax or not isinstance(syntax, str):
            return prompts
        to_filter = set()
        syntax = syntax.lower()
        for p, prompt in prompts.items():
            if not prompt.required_syntax:
                continue
            valid_syntax = [syn.lower() for syn in prompt.required_syntax]
            if syntax not in valid_syntax:
                to_filter.add(p)
        return {k: v for k, v in prompts.items() if k not in to_filter}

    def get_endpoints_for_prompt(self, prompt: Prompt) -> Dict[str, Endpoint]:
        """
        Returns all loaded usable endpoints for a given prompt
        """
        to_filter = set()
        valid_eps = [ep.lower() for ep in prompt.required_endpoints]
        for e in self.endpoints:
            # if prompt requires endpoints, filter all other endpoints
            if valid_eps and e.lower() not in valid_eps:
                to_filter.add(e)
            # filter any endpoint for which valid_params doesn't contains any provided param by the prompt
            for p in prompt.params:
                if p not in self.endpoints[e].valid_params:
                    to_filter.add(e)
                    break
            # filter any endpoint for which any required vars is not provided by prompt
            # TODO: filter also endpoint for which don't accept any var provided by prompt?
            for rv in self.endpoints[e].required_vars:
                if rv not in prompt.variables:
                    to_filter.add(e)
                    break
        return {k: v for k, v in self.endpoints.items() if k not in to_filter}
