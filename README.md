# AssistantAI

A Sublime Text plugin.

This plugin is a general purpose implementation of an HTTP API client that allows perform text manipulation with remote API responses, as a result to requests based on selected text and optional user input.

A common use case is to consume API of, for instance, Generative AI like ChatGPT or OpenAI Codex, to complete, edit, comment or explain selected code chunks. Another example is to consume GitHub, Gitea or similar VCS server's API to add Issues, PR and similar workflows while you code. 

<p align="center">
	<img src="screenshot.gif" alt="AssistantAI in action"></img>
</p>

AssistantAI can be extended by the user or by other packages, providing servers, endpoints, prompt templates and credentials placeholders, defined in Sublime Settings files, in JSON.

# Usage

Once installed, invoke `AssistantAI` from the command palette, select a prompt from the presented list and follow it's flow.

Prompts are offered based on the context (configured servers, selected text, buffer syntax, available content, etc.), and as per specifications provided by the prompt it self.

Without any configured server, there will be no prompts available.

The general flow is simple. For instance:

- Select a text region (i.e.: A code function, or Markdown section).
- Command Palette > `AssistantAI` (or the keyboard shortcut if you set up one).
- Select a **prompt**.
- If the prompt needs additional **inputs**, those will be requested using the UI.
- When several **servers** with valid **endpoints** qualifies for the selected prompt, a list of endpoints is presented.

Once AssistantAI have a prompt, with all needed inputs and the target endpoint is selected, it builds an HTTP payload based on that and makes the network request.

The response is parsed based on the endpoint specification and its specified **command** is executed.

The prompt may specify another action instead of text manipulation (replace, append, insert), such as show the response in an Output Panel, or a new Buffer.

As an example, consider this flow using the bundled OpenAI server endpoints definition (requires credentials) plugin while editing a Python file:

- Select a python function
- Ask AssistantAI for the prompt "Add python docstring"
- *Since only one endpoint qualifies, a request is made to OpenAI without further inputs*
- The python docstring is added to the selected function as returned by ChatGPT

# What's included with this plugin?

The plugin implements the parser of the settings files where the servers, prompts and credentials are configured (by this package, another package, or the user). Manages the filtering of the prompts that are available given a context, and takes care of the API requests, building payloads, parsing responses, and performing the text manipulation.

Besides the plugin implementation, AssistantAI includes the following definitions of servers and prompts.

## Servers

Servers are definitions of network resources that AssistantAI can consume using HTTP requests. Includes the URL, timeout and a description.

Each server must specify one or more endpoints which includes what are the possible request payloads structures, declarative instructions on how to build it based on the prompt user inputs (i.e.: selected text, or additional inputs the user is prompted for).

AssistantAI reads the configuration seeking for servers definitions, and considers a server to be available when all required credentials are configured by the user (i.e.: API TOKENS).

AssisntantAI includes currently the following server and endpoints definitions.

### OpenAI

OpenAI server definition that allows consuming the API with three end points:

- Edits
- Completions
- Chat completions (the one powering ChatGPT)

### Gitea

Gitea is an open source replacement of GitHub, less sophisticated and much lightweight, which you can deploy in your own infrastructure. It provides an API to interact with it, allows among many other workflows, to create repositories, Issues and PRs.

This Server definition is WIP yet to be released. 

## Prompts

Prompts are request templates that the user must fill with the variables when editing using Sublime Text. It's a straight forward process.

The required variables are quite flexible and typically includes `text`, representing the selected text, if any.

Once the user invokes a prompt, it must resolve all required inputs if not yet solved automatically. 

A request is then build and send to the available endpoint, or the one selected by the user if more than one is available.

For instance, if only `text` is required by the prompt, the user must have selected text for the prompt to be usable. 

If the prompt is limited to `syntax` (i.e.: Python), the current buffer must be from that required syntax.

Available prompts out of the box with AssistantAI includes the following.

### OpenAI

A set of generic prompts are provided if OpenAI server is enabled (i.e.: credentials are configured):

- Continue text from end of selection
- Ask to make a change on selection
- Ask to make a change on selection using Chat end point

Those prompts requires at least one server endpoint that accepts `text` as input, or `text` + `instruction`.

### Python

A set of prompts commonly used while editing python code are bundled in AssistantAI.

- **Add docstring**: selecting a python function and invoking this prompt, a request will result in the python function being populated with a `docstring`.
- **Add comments**: will comment line by line the selected python code.
- **Explain**: will open the output panel with a verbose explanation of the selected code.

Those prompts requires at least one server that accepts `text` as input.

# Installation

The plugin is intended to be published in Package Control. When published, further instructions will be given here.

Install this plugin and you will have available the following:

- The `AssistantAI` command in the command palette.
- `Settings` > `Package Settings` > `AssistantAI` > `Settings`.
- `Settings` > `Package Settings` > `AssistantAI` > `Key Bindings` (the default is commented).
- The servers and prompts described in previous section.

Currently, at the very least, you should configure the API KEY of OpenAI to play with the plugin.

## Settings

In settings you can add you own server definitions, prompt specifications, and the endpoint credentials like API tokens and keys.

Everything can be configured with Sublime JSON settings with a very high degree of flexibility.

## Key Bindings

A default example of a key binding is provided to bind a keyboard shortcut to AssistantAI command, so you can quickly get the available prompt list based on the current context.

## AssistantAI command

If no prompts are available, `AssistantAI` command does nothing else than show a status bar message warning.

# Adding Servers and Prompts

You can add your own servers using JSON settings (i.e.: `Settings` > ... > `AssistantAI` > `Settings`), but the intended use is to install AssistantAI plugins that provides complex and reusable server and prompt specifications.

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

There are four types of valuable contributions:

- Share your experience and creativity by opening Issues with bug reports and feature requests.
- Send PR to improve or fix the code. Ideally, as a response of an open issue.
- Add Servers, Prompts providing a specific and working `assistant_ai_{NAME}.sublime-settings` file. Ideally using a PR.
- Developing a Sublime Text plugin (or updating your current one) that provides a `assistant_ai_{NAME}.sublime-settings`.

For an example `assistant_ai_{NAME}.sublime-settings` check the [OpenAI settings](assistant_ai_openai.sublime-settings) files that includes prompts and server endpoints specifications.

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
- Reading the docs from Sublime API reference and Package Control docsAssistantAI
[screenshort.gif]: 
