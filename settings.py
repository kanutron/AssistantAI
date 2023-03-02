import sublime
import uuid

SETTINGS_FILE = 'assistant_ai.sublime-settings'

class AssistantAISettings:
    '''
    Handles all AssistantAI settings.
    '''
    config: sublime.Settings
    credentials = {}
    servers = {}
    endpoints = {}
    prompts = {}

    def load(self):
        self.load_config()
        self.load_configured_credentials()
        self.load_enabled_servers()
        self.load_enabled_endpoints()
        self.load_usable_prompts()

    def load_config(self):
        self.config = sublime.load_settings(SETTINGS_FILE)

    def load_configured_credentials(self):
        '''
        Loads all configured credentials. User must speicify those credentials.
        If they are not specified, servers that requires that credentials will
        be dismissed.
        '''
        creds_all = self.get('credentials', {})
        creds = {}
        for cid, cred in creds_all.items():
            if cred is not None:
                creds[cid] = cred
        for c in creds:
            print(f'Credential: {c}') # DEBUG
        self.credentials = creds

    def load_enabled_servers(self):
        '''
        Loads all usable servers with valid credentials or
        those don't require any credential.
        '''
        servers_user = self.get('servers', {})
        servers_def = self.get('servers_default', {})
        servers_packages = {} # TODO: load servers specified by packages
        servers_all = self.merge_dicts(servers_def, servers_packages)
        servers_all = self.merge_dicts(servers_all, servers_user)
        # once we have all servers, filter to usable ones
        servers = {}
        servers_to_dismiss = []
        for sid, server in servers_all.items():
            if not 'requires_credentials' in server:
                servers[sid] = server  # this server requires no credentials
            if isinstance(server['requires_credentials'], str):
                server['requires_credentials'] = [server['requires_credentials'],]
            for req_cred in server['requires_credentials']:
                if req_cred not in self.credentials:
                    servers_to_dismiss.append(sid)
            if sid not in servers_to_dismiss:
                servers[sid] = server
        # DEBUG
        for s in servers:
            print(f'Server: {s}')
        self.servers = servers

    def load_enabled_endpoints(self):
        '''
        Loads all enabled endpoints in a list for the servers that usable.
        '''
        endpoints = {}
        for sid, server in self.servers.items():
            for eid, endpoint in server.get('endpoints', {}).items():
                for sk in server:
                    if sk not in ('name', 'description', 'endpoints'):
                        endpoint[sk] = server[sk]
                endpoints[f'{sid}/{eid}'] = endpoint
        # DEBUG
        for e in endpoints:
            print(f'Endpoint: {e}')
        self.endpoints = endpoints

    def load_usable_prompts(self):
        '''
        Loads all configured prompts that requires valid available endpoints or
        requires no specific endpoints.
        '''
        prompts_user = self.config.get('prompts', [])
        prompts_def = self.config.get('prompts_default', [])
        prompts_packages = [] # TODO: load prompts specified by packages
        prompts_all = prompts_def + prompts_user + prompts_packages
        # once we have all prompts, filter to usable ones
        prompts = {}
        for prompt in prompts_all:
            pid = prompt.get('id', str(uuid.uuid4()))
            if not 'required_endpoints' in prompt:
                prompts[pid] = prompt
                continue
            if isinstance(prompt['required_endpoints'], str):
                prompt['required_endpoints'] = [prompt['required_endpoints'],]
            for req_ep in prompt['required_endpoints']:
                if req_ep in self.endpoints:
                    prompts[pid] = prompt
                else:
                    prompt['required_endpoints'].remove(req_ep)
        # process prompt imports
        self.prompts = {}
        self.prompts.update(prompts)
        for p, prompt in prompts.items():
            proc_prompt = self.prompt_import(p, prompt)
            if proc_prompt:
                self.prompts[p] = proc_prompt
            else:
                del(self.prompts[p])
        # DEBUG
        for p in self.prompts:
            print(f'Prompt: {p}')

    def prompt_import(self, p, prompt, chain=None):
        '''
        Given a promt as specified in settings, process the import statement
        resulting in the intended prompt with all keys populated.

        Is a recursive function for resolving the dependency tree of prompts.

        Cyclic dependency safe.
        '''
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
            # recursivelly call this function later
            del(prompt['import'])
            return prompt
        # chain check for duplicates = cyclic dependency
        if parent_id in chain:
            return None
        chain.append(parent_id)
        # specified parent id doesn't exist
        if parent_id and parent_id not in self.prompts:
            return None
        # get the parent
        parent = self.prompts.get(parent_id, {})
        if not parent:
            return None
        # process parent import if needed
        if parent.get('import', None):
            parent = self.prompt_import(parent_id, parent, chain)
        # process current prompt
        if parent:
            self.prompts[parent_id] = parent
            return self.get_imported_prompt(prompt, parent, import_spec)
        return None

    def get_imported_prompt(self, prompt, parent, import_spec):
        '''
        Given a promt, its parent and the import specification, return the
        prompt processed as per the import specs.

        Parent must not have the import key. That is, if the parent depends on
        another ancestor, that should be resolved first.
        '''
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
            if not new[key]:
                del(new[key])
        return new

    def get_prompts_by_edit_state(self, edit):
        '''
        Returns all usable prompts filtering by current edit state.
        Seleteced text, available context pre and/or post contents.
        '''
        # TOOD: implement this.
        return self.prompts

    def get_prompts_by_syntax(self, syntax):
        '''
        Returns all loaded usable prompts filtering by syntax
        '''
        prompts = {}
        for p, prompt in self.prompts.items():
            if syntax in prompt.get('required_syntax', [syntax, ]):
                prompts[p] = prompt
        return prompts

    def get_endpoints_for_prompt(self, prompt_id):
        '''
        Returns all loaded usable endpoints for a given prompt
        '''
        endpoints = {}
        for e, endpoint in self.endpoints.items():
            if prompt_id in endpoint.get('required_endpoints', [prompt_id, ]):
                endpoints[e] = endpoint
        return endpoints

    def get(self, key, default=None):
        return self.config.get(key, default)

    @staticmethod
    def merge_dicts(old, new) -> dict:
        for k, v in old.items():
            if k in new:
                v.update(new[k])
            new[k] = v
        return new
