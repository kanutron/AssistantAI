# AssistantAI Sublime Text plugin

This Sublime Text plugin is a general purpose implementation of an HTTP API client that allows to perform text manipulation with remote API responses, as a result to a request based on selected text and optional user input.

A common use case is to consume API for Generative AI like ChatGPT or OpenAI Codex to complete, edit, comment or explain selected code chunks.

The usage is simple:

- Select a text region (i.e.: A code function or Markdown section)
- Hit the configured key map (or Command Palette > AssistantAI)
- Ask for `AssistantAI` command
- AssistantAI will show a quick panel with available **prompts**
- Choose the desired prompt and, if the prompt needs, **inputs**, those will be requested using UI
- When several **servers** with valid **endpoints** qualifies for the selected prompt and the current context (syntax, selections, inputs, etc.), a list of endpoints is given.

Once AssistantAI have a prompt, all needed inputs and an endpoint is selected, it builds an HTTP request based on that and makes the network request.

The response is parsed based on the endpoint specification and the specified **AssistantAI command** is executed.

As an example, consider this flow using `AssistantAI-OpenAI` plugin:

- Select a python function
- Ask AssistantAI for the prompt "Add python docstring"
- Since only one endpoint qualifies, a request is made to OpenAI without further inputs
- The python docstring is added to the selected function as returned by ChatGPT

# Installation

Install this plugin and you will have available the following:

- `Settings` > `Package Settings` > `AssistantAI` > `Settings`
- `Settings` > `Package Settings` > `AssistantAI` > `Key Bindings`

The `AssistantAI` command in the command palette.

TODO: publish in package control so installation is straight forward.

## Settings

In settings you can add you own server definitions, prompt specifications, and the endpoint credentials like API tokens and keys.

Everything can be configured with Sublime JSON settings with a very high degree of flexibility.

## Key Bindings

A default example of a key binding is provided to bind a keyboard shortcut to AssistantAI command, so you can quickly get the available prompt list based on the current context.

## AssistantAI command

If no prompts are available, `AssistantAI` command does nothing else than show a status bar message warning.

# Adding Servers and Prompts

You can add your own servers using JSON settings (i.e.: `Settings` > ... > `AssistantAI` > `Settings`), but the intended use is to install AssistantAI plugins that provides complex and reusable server and prompt specifications.

Check out these plugins:

- **AssistantAI-OpenAI**: provides server and endpoint specifications to OpenAI text completion, edits and chat completions end points and basic prompts for interacting with ChatGP. [GitHub](https://github.com/kanutron/AssistantAI-OpenAI)
- **AssistantAI-Python**: provides prompt specification to make Python code manipulation using any available endpoint compatible with those prompt specifications. OpenAI server is one of those compatible endpoints. [GitHub](https://github.com/kanutron/AssistantAI-Python)

# Understanding the concepts

This plugin uses 4 types of setting specifications:

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

## Prompt

A prompt is a configured set of inputs and variables needed to make the request

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
- `create` a new buffer with the response.

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

### Server endpoints

Specification of the request and expected response.

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