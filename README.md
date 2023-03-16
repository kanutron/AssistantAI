# AssistantAI Sublime Text plugin

This Sublime Text plugin is a general purpose implementation of an HTTP API client that allows to perform text manipulation with remote API responses, as a result to requests based on selected text and optional user input.

A common use case is to consume API for Generative AI like ChatGPT or OpenAI Codex to complete, edit, comment or explain selected code chunks.

AssistantAI requires additional plugins where the actual server and prompt templates are provided. Everything is configured in Sublime Settings JSON files, including servers, endpoints, prompt templates and credentials.

Check these AssistantAI plugins:

- [**AssistantAI-OpenAI**](https://github.com/kanutron/AssistantAI-OpenAI): provides specifications of OpenAI servers and the edits, completions, and chat endpoints. Also provides basic prompts for interacting with ChatGPT and their text models.
- [**AssistantAI-Python**](https://github.com/kanutron/AssistantAI-Python): provides prompt specification to make Python code manipulation using any available endpoint compatible with those prompt specifications. OpenAI server is one of those compatible endpoints. 

# Usage

Once you installed AssistantAI and at least one plugin providing Server specification, you will be able to use it.

The general usage is simple:

- Select a text region (i.e.: A code function or Markdown section).
- Hit the configured key map (or Command Palette > AssistantAI).
- `AssistantAI` will show a quick panel with available **prompts**.
- Choose the desired prompt. If the prompt needs, **inputs**, those will be requested using UI.
- When several **servers** with valid **endpoints** qualifies for the selected prompt and the current context (syntax, selections, inputs, etc.), a list of endpoints is given.

Once AssistantAI have a prompt, all needed inputs and the endpoint is selected, it builds an HTTP request based on that and makes the network request.

The response is parsed based on the endpoint specification and the specified **AssistantAI command** is executed.

As an example, consider this flow using `AssistantAI-OpenAI` plugin while editing a Python file:

- Select a python function
- Ask AssistantAI for the prompt "Add python docstring"
- *Since only one endpoint qualifies, a request is made to OpenAI without further inputs*
- The python docstring is added to the selected function as returned by ChatGPT

# Installation

Install this plugin and you will have available the following:

- `Settings` > `Package Settings` > `AssistantAI` > `Settings`
- `Settings` > `Package Settings` > `AssistantAI` > `Key Bindings`

The `AssistantAI` command in the command palette.

==TODO==: publish in package control so installation is straight forward.

## Settings

In settings you can add you own server definitions, prompt specifications, and the endpoint credentials like API tokens and keys.

Everything can be configured with Sublime JSON settings with a very high degree of flexibility.

## Key Bindings

A default example of a key binding is provided to bind a keyboard shortcut to AssistantAI command, so you can quickly get the available prompt list based on the current context.

## AssistantAI command

If no prompts are available, `AssistantAI` command does nothing else than show a status bar message warning.

# Adding Servers and Prompts

You can add your own servers using JSON settings (i.e.: `Settings` > ... > `AssistantAI` > `Settings`), but the intended use is to install AssistantAI plugins that provides complex and reusable server and prompt specifications.

- **AssistantAI-OpenAI** [here](https://github.com/kanutron/AssistantAI-OpenAI)
- **AssistantAI-Python** [here](https://github.com/kanutron/AssistantAI-Python)

# Understanding the concepts

This plugin uses 4 types of specifications.

- Servers
- Server Endpoints
- Credentials
- Prompts

## Server

A server is a JSON specification that includes the URL, the needed headers and required credentials keys, and a set of endpoints.

```json
{
	"id": "openai",
	"name": "OpenAI",
	"url": "https://api.openai.com:443",
	"timeout": 60,
	"required_credentials": ["api_key"],
	"headers": {
		"Authorization": "Bearer ${api_key}",
		"Content-Type": "application/json",
		"cache-control": "no-cache",
	},
	"endpoints": { ... }
},
```

If the server specifies a required credential (like `api_key` in this case), and this credential is not configured by the user, the server will be not available. Any prompt that explicitly requires endpoints of this server will be unavailable.

Headers to be sent to the server may include the credentials configured by the user. They will be expanded by Sublime Text when creating the HTTP request.

### Server endpoints

Specification of the request and expected response. It is included in the `endpoints` key of a server specification.

Each server may provide one or more endpoints.

`request` key provides the JSON object to be built by AssistantAI to send the request to the server's endpoint.

`response` specifies two keys:

- `error`: for the key where any error will be retrieved
- `output`: the path (forward slashes `/` as a separator) where to retrieve the text

```json
{
	"chat_completions": {
		"name": "Chat Completions",
		"method": "POST",
		"resource": "/v1/chat/completions",
		"required_vars": ["text"],
		"valid_params": {
			"model": "string",
			"messages": "string",
			...
			"user": "string",
		},
		"request": {
			"model": "gpt-3.5-turbo",
			"messages": [
				{
					"role": "user",
					"content": "${text}",
				}
			],
		},
		"response": {
			"error": "error",
			"output": "choices/0/message/content",
		},
	}
}
```

## Credentials

They are key-value pairs used by server endpoints. Configured on each plugin settings file. 

If you install **AssistantAI-OpenAI** plugin you will have to setup this:

```json
{
	"credentials": {
		"api_key": "sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXx"
	},
}
```

The key `api_key` is later used by the server specification as a variable that will be expanded in a HTTP header.

Each AsistantAI plugin providing a server specification (like AssistantAI-OpenAI) will require you to set up the credentials in your user-defined settings in order to enable the server. 

## Prompt

A prompt is a configured set of inputs and variables needed to build a request based on user text selection and additional inputs.

Prompts are context aware, accounting for selected text, available pre- and post-text, syntax of the current buffer, and configured server endpoints.

If a prompt declares that needs an endpoint, that prompt will be shown only if that endpoint is available.

Similarly if a prompt declares is valid for `python` syntax, will be shown only when editing a python file.

When a prompt requires `text` input, and no selection is made, that prompt will not be shown.

```json
{
	"id": "continue_selected_text",
	"name": "Continue selected text",
	"description": "Given a selected text, continue writing from there.",
	"required_inputs": ["text"],
	"required_endpoints": [
		"openai/completions",
		"openai/chat_completions"
	],
	"params": {
		"temperature": 1.0,
		"max_tokens": 1800,
	},
	"command": "append",
}
```

### Prompt command

Once a prompt is executed and a response is obtained, a command is executed as per the prompt specification.

Command can be;

- `replace` the entire selection
- `append` at the end of selection
- `insert` replacing a placeholder
- `output` to a new bottom panel
- `create` a new buffer with the response

# Contributing

If you want to contribute, feel free to open an Issue or send your PR.

The code is pretty much tidy now. But there are some missing features like:

- Import statement for Server specifications
- Proper documentation for AssistantAI plugin developers
- JSON schema for Server and Prompts
- Testing Sublime Versions other than `4143 macOS`
- Implementing other plugins such as GitHub, Gitea and similar to interact with their APIs.
- Implementing super cool prompts for Markdown, Java, Rust, ...
- Improving Quick Panel inputs 

# License

This software is released under MIT license.

# Disclaimer

This is my first Sublime Text plugin and probably is full of bugs.

This plugin is complex to setup. Once properly done, the usage is straight forward though. A good documentation is key for increasing adoption. 

# Contact

My twitter accounts is @kanutron, and although I'm not super active there, I receive push notification on DM.

# Credits

I been learning to code Sublime Text plugins by:

- Reading the code from CodexAI plugin from OpenAI
- Reading the code from https://github.com/yaroslavyaroslav/OpenAI-sublime-text/tree/master
- Interacting with ChatGPT (using this plugin!)
- Reading the docs from Sublime API reference and Package Control docs