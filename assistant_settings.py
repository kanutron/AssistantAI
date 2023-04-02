import sublime
import uuid

PKG_NAME = 'AssistantAI'
SETTINGS_FILE = 'assistant_ai.sublime-settings'
PKG_SETTINGS_FILE_BLOB = 'assistant_ai*.sublime-settings'

class AssistantAISettings:
    """
    Handles all AssistantAI settings.
    """
    endpoints = {}
    prompts = {}
    settings_callbacks = {}

    def load(self):
        """
        Loads settings and prompts from all packages that provides AssistantAI settings.
        Any package providing assistant_ai*.sublime-settings will be processed.

        Each package provided endpoints can only use credentials from its own settings files
        but can rely on other packages configured end points.

        :return: None
        """
        # Get all settings from all packages that provides AssistantAI settings.
        files = set()
        for resource in sublime.find_resources(PKG_SETTINGS_FILE_BLOB):
            files.add(resource.split('/')[-1])
        # load endpoints for each settings file.
        for file in files:
            settings = self.load_settings_from(file)
            credentials = self.load_credentials_from(settings)
            servers = self.load_servers_from(settings, credentials)
            # update endpoints
            eps = self.load_endpoints_from(servers)
            self.endpoints.update(eps)
        # load prompts now that we have all end points loaded.
        for file in files:
            settings = self.load_settings_from(file)
            self.prompts.update(self.load_prompts_from(settings))
        # since some prompts may import from others, process the import statements
        self.prompts = self.process_prompts_import(self.prompts)

    def unload(self):
        """
        Clears all the 'assistant_ai' settings on_change callbacks from the
        `settings_callbacks` dictionary.

        :return: None
        """
        for file in self.settings_callbacks:
            self.settings_callbacks[file].clear_on_change('assistant_ai')

    def load_settings_from(self, file):
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

    def load_credentials_from(self, settings):
        """
        Extracts valid credentials from settings.

        :param settings: A dictionary containing credentials data.
        :return: A dictionary containing valid credentials.
        """
        creds_all = settings.get('credentials', {})
        if not isinstance(creds_all, dict):
            return {}
        creds = {}
        for cid, cred in creds_all.items():
            if cred is not None:
                creds[cid] = cred
        return creds

    @staticmethod
    def get_credentials_for(server, credentials):
        creds = {}
        sid = None
        if isinstance(server, dict):
            sid = server.get('id')
        if sid and sid in credentials and isinstance(credentials[sid], dict):
            creds.update(credentials[sid])
        elif isinstance(credentials, dict):
            creds.update(credentials)
        return {k:v for k,v in creds.items() if isinstance(v, str)}

    def load_servers_from(self, settings, credentials):
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
        servers_all = []
        servers_def = settings.get('default_servers', [])
        if isinstance(servers_def, list):
            servers_all += servers_def
        servers_user = settings.get('servers', [])
        if isinstance(servers_user, list):
            servers_all += servers_user
        if not servers_all:
            return {}
        # process imports before anything else
        for i, server in enumerate(servers_all):
            servers_all[i] = AssistantAISettings.process_server_import(server, servers_all)
        # filter to usable ones by available credentials
        servers = {}
        servers_to_dismiss = []
        for server in servers_all:
            sid = server.get('id', 'server_' + str(uuid.uuid4()))
            if not 'required_credentials' in server:
                servers[sid] = server
                continue  # this server requires no credentials
            # ensure this server have all needed credentials, dismissit otherwise
            if isinstance(server['required_credentials'], str):
                server['required_credentials'] = [server['required_credentials'],]
            srv_creds = AssistantAISettings.get_credentials_for(server, credentials)
            for req_cred in server['required_credentials']:
                if req_cred not in srv_creds or not srv_creds.get(req_cred):
                    servers_to_dismiss.append(sid)
                    break
            # process server headers expanding any needed credential and add the server
            if sid not in servers_to_dismiss:
                headers = {}
                template = server.get('headers', {})
                for k, v in template.items():
                    headers[k] = sublime.expand_variables(v, srv_creds)
                server['headers'] = headers
                server['credentials'] = srv_creds
                # add this server
                servers[sid] = server
            else:
                print(f"Server {sid} dismissed due to missing credentials.")
        return servers

    @staticmethod
    def process_server_import(server, servers):
        if 'import' not in server:
            return server
        if not isinstance(server['import'], str):
            del(server['import'])
            return server
        import_ref = server.get('import', '').strip().lower()
        for parent in servers:
            candidate_ref = parent.get('id', '').strip().lower()
            if candidate_ref != import_ref:
                continue
            new = {}
            new.update(parent)
            new.update(server)
            if 'import' in new:
                del(new['import'])
            return new
        if 'import' in server:
            del(server['import'])
        return server

    def load_endpoints_from(self, servers):
        """
        Load all available endpoints from given servers and process their headers.

        :param servers: A dictionary containing information about servers.
        :type servers: dict
        :return: A dictionary containing available endpoints with processed headers.
        :rtype: dict
        """
        # all server keys except those banned will be added into endpoint
        endpoints = {}
        banned_server_keys = ('name', 'description', 'endpoints')
        for sid, server in servers.items():
            # iterate over each endpoint in the current `server`
            for eid, endpoint in server.get('endpoints', {}).items():
                new_ep = {}
                new_ep.update(endpoint)
                # iterate over each key in the current `server`
                for sk in server:
                    if sk not in banned_server_keys:
                        new_ep[sk] = server[sk]
                # add the server related keys with the prefix 'server_'
                new_ep['server_name'] = server.get('name', '')
                new_ep['server_description'] = server.get('description', '')
                endpoints[f'{sid}/{eid}'] = new_ep
        return endpoints

    def load_prompts_from(self, settings):
        """
        This function loads prompts from the settings file and filters out prompts that require unavailable endpoints.
        Then, it ensures that variables are configured with defaults, so each input produces a variable.

        Args:
        - settings: dictionary containing all settings

        Returns:
        - prompts: dictionary containing all prompts that were not filtered out and have default variables
        """
        prompts_all = []
        prompts_def = settings.get('default_prompts', [])
        if isinstance(prompts_def, list):
            prompts_all += prompts_def
        prompts_user = settings.get('prompts', [])
        if isinstance(prompts_user, list):
            prompts_all += prompts_user
        if not prompts_all:
            return {}
        prompts = {}
        for prompt in prompts_all:
            pid = prompt.get('id', 'prompt_' + str(uuid.uuid4()))
            if not 'required_endpoints' in prompt:
                prompts[pid] = prompt
                continue
            if isinstance(prompt['required_endpoints'], str):
                prompt['required_endpoints'] = [prompt['required_endpoints'],]
            for req_ep in prompt['required_endpoints']:
                if req_ep in self.endpoints:
                    prompts[pid] = prompt
            # ensure the prompt provides a 'vars' key
            for pid, prompt in prompts.items():
                prompt_vars = prompt.get('vars', {})
                if prompt_vars:
                    continue
                required_inputs = prompt.get('required_inputs', ['text',])
                for r in required_inputs:
                    prompt_vars[r] = f'${{{r}}}'
                prompts[pid]['vars'] = prompt_vars
        return prompts

    def process_prompts_import(self, prompts):
        """
        This function processes all loaded prompts returns a dictionary of processed prompts.
        For each prompt, process the 'import' statement if needed.

        Parameters:
        prompts (dict): A dictionary containing prompts to be processed.

        Returns:
        dict: A dictionary containing processed prompts.
        """
        processed = {}
        processed.update(prompts)
        for p, prompt in prompts.items():
            proc_prompt = self.prompt_import(processed, prompt)
            if proc_prompt:
                processed[p] = proc_prompt
            else:
                del(processed[p])
        return processed

    @staticmethod
    def prompt_import(prompts, prompt, chain=None):
        """
        Given a promt as specified in settings, process the import statement
        resulting in the intended prompt with all keys populated from its parent.

        Is a recursive function for resolving the dependency tree of prompts.

        Cyclic dependency safe.
        """
        if not isinstance(chain, list):
            chain = []
        import_spec = prompt.get('import', None)
        if not import_spec:
            return prompt
        if isinstance(import_spec, str):
            import_spec = {'from': import_spec}
        if not isinstance(import_spec, dict):
            return None
        parent_id = import_spec.get('from', None)
        # there is an import, without a from id
        if not parent_id:
            # delete import key as its presence is used to determine the need to
            # recursively call this function later
            del(prompt['import'])
            return prompt
        # chain check for duplicates = cyclic dependency
        if parent_id in chain:
            return None
        chain.append(parent_id)
        # specified parent id doesn't exist
        if parent_id and parent_id not in prompts:
            return None
        # get the parent
        parent = prompts.get(parent_id, {})
        if not parent:
            return None
        # process parent import if needed
        if parent.get('import', None):
            parent = AssistantAISettings.prompt_import(prompts, parent, chain)
        # process current prompt
        if parent:
            prompts[parent_id] = parent
            return AssistantAISettings.get_imported_prompt(prompt, parent, import_spec)
        return None

    @staticmethod
    def get_imported_prompt(prompt, parent, import_spec):
        """
        Given a prompt, its parent and the import specification, return the
        prompt processed as per the import specs.

        Parent must not have the import key. That is, if the parent depends on
        another ancestor, that should be resolved first.
        """
        actions = {
            'required_inputs': 'replace',
            'required_context': 'replace',
            'required_syntax': 'update',
            'required_endpoints': 'update',
            'required_prompt_responses': 'update',
            'provided_vars': 'update',
            'provided_params': 'update'
        }
        new = {}
        new.update(parent)
        new.update(prompt)
        del(new['import'])
        # fine tune how import happens, for object/array items
        # this is defined by the user in the 'import' key
        for key, action in actions.items():
            parent_v = parent.get(key)
            prompt_v = prompt.get(key)
            if not parent_v or not prompt_v:
                continue
            action = import_spec.get(key, action)
            if action == 'replace':
                continue
            if action == 'delete':
                del(new[key])
                continue
            if isinstance(parent_v, list) and isinstance(prompt_v, list):
                new[key] = parent_v + prompt_v
                continue
            if isinstance(parent_v, dict) and isinstance(prompt_v, dict):
                new[key] = parent_v.update(prompt_v)
                continue
        return new

    def filter_prompts_by_available_context(self, prompts, available_context):
        """
        Returns all usable prompts filtering by current edit state.
        Selected text, available context pre and/or post contents.
        """
        to_filter = set()
        for p, prompt in prompts.items():
            if 'text' in prompt.get('required_inputs', ['text',]):
                if available_context.get('text_chars') < 1:
                    to_filter.add(p)
                    continue
            if 'required_context' not in prompt:
                continue
            req_crx = prompt.get('required_context')
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

    def filter_prompts_by_available_endpoints(self, prompts):
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

    def filter_prompts_by_syntax(self, prompts, syntax=None):
        """
        Returns all loaded usable prompts filtering by syntax
        """
        if not syntax or not isinstance(syntax, str):
            return prompts
        to_filter = set()
        syntax = syntax.lower()
        for p, prompt in prompts.items():
            prompt_syntax = prompt.get('required_syntax', [syntax, ])
            valid_syntax = [syn.lower() for syn in prompt_syntax]
            if syntax not in valid_syntax:
                to_filter.add(p)
        return {k: v for k, v in prompts.items() if k not in to_filter}

    def get_endpoints_for_prompt(self, prompt):
        """
        Returns all loaded usable endpoints for a given prompt
        """
        endpoints = {}
        # get all endpoints
        for e, endpoint in self.endpoints.items():
            endpoints[e] = endpoint
        # if prompt requires endpoints, filter all other endpoints
        required_eps = prompt.get('required_endpoints')
        if required_eps:
            valid_eps = [ep.lower() for ep in required_eps]
            for e, endpoint in self.endpoints.items():
                if e not in endpoints:
                    continue
                if e.lower() not in valid_eps:
                    del(endpoints[e])
        # filter any endpoint for which valid_params doesn't contains any provided param by the prompt
        params = prompt.get('params')
        if params:
            for e, endpoint in self.endpoints.items():
                if e not in endpoints:
                    continue
                for p in params:
                    if p not in endpoint.get('valid_params', {}):
                        del(endpoints[e])
        # filter any endpoint for which any required vars is not provided by prompt
        prompt_vars = prompt.get('vars')
        if prompt_vars:
            for e, endpoint in self.endpoints.items():
                if e not in endpoints:
                    continue
                for rv in endpoint.get('required_vars'):
                    if rv not in prompt_vars:
                        del(endpoints[e])
        return endpoints
