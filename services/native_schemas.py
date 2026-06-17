# Native Tool Calling Schemas for XOYO

NATIVE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_bash",
            "description": "Runs ANY terminal command on the Linux host machine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Writes code or text to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file"},
                    "content": {"type": "string", "description": "The content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Robust web search using DuckDuckGo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_url_content",
            "description": "Reads text content from a URL using BeautifulSoup.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to scrape"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists all files and subdirectories in a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the directory"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Uses grep to search for a string pattern within files in a specified directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The text pattern to search for"},
                    "path": {"type": "string", "description": "The directory to search in"}
                },
                "required": ["query", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_artifact",
            "description": "Writes a beautiful Markdown artifact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Name of the artifact (e.g. plan.md)"},
                    "content": {"type": "string", "description": "Markdown content"}
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_artifact",
            "description": "Reads an existing Markdown artifact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Name of the artifact"}
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_subagent",
            "description": "Spawns a subagent swarm concurrently.",
            "parameters": {
                "type": "object",
                "properties": {
                    "roles": {"type": "array", "items": {"type": "string"}, "description": "Roles of the subagents"},
                    "prompts": {"type": "array", "items": {"type": "string"}, "description": "Task prompts for each subagent"}
                },
                "required": ["roles", "prompts"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_automation_service",
            "description": "Invokes XOYO's advanced massive automation microservices (e.g. whatsapp, instagram).",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "The automation service (whatsapp, instagram, etc)"},
                    "endpoint": {"type": "string", "description": "The HTTP endpoint path (e.g. /send_message)"},
                    "payload": {"type": "object", "description": "The JSON payload"}
                },
                "required": ["service_name", "endpoint", "payload"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "final_answer",
            "description": "Call this tool when you have completed the task and want to give the final answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string", "description": "Your final summary of what you did and the results."}
                },
                "required": ["answer"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "view_image",
            "description": "Views an image natively using multimodal vision and returns a description of the image content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the image file"}
                },
                "required": ["path"]
            }
        }
    }
]
