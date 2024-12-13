"""
title: Ollama + LangSmith Tracing Pipeline
author: DomPolizzi (Poelyte)
Github: https://github.com/DomPolizzi
date: 2024-12-12
version: 0.0.1
license: MIT
description: A pipeline for retrieving responses from Ollama and sending tracing information to LangSmith.
note: STILL A WIP, Traces aren't exactly working as we want.
requirements: langsmith==0.2.2
"""

import json
import os
import uuid
from datetime import datetime, timezone
import requests
from schemas import OpenAIChatMessage
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from langsmith import Client, traceable, RunTree
from utils.pipelines.main import get_last_user_message, get_last_assistant_message

class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        api_url: str
        api_key: str

    def __init__(self):
        self.type = "filter"
        self.name = "Langsmith Filter"
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
                "api_key": os.getenv("LANGSMITH_API_KEY", "KEY_HERE"),
                "api_url": os.getenv("LANGSMITH_URL", "URL_HERE"),
            }
        )
        self.run_id = None

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """Process incoming request and create LangSmith trace."""
        print(f"Inlet initialized for {__name__}")
        print(f"User: {user}")
###        print(f"Body: {body}")  # Add debug logging
        
        if not body or not isinstance(body, dict):
            print("Invalid body format")
            return body

        try:
            messages = body.get("messages", [])  # Use the top-level "messages" list
            last_user_message = get_last_user_message(messages)
            
            if last_user_message is None:
                print("No valid user message found")
                return body
            
            user_info = {
                'id': user.get('id') if user else None,
                'name': user.get('name') if user else None,
                'email': user.get('email') if user else None
            }

            # Ensure you're sending the message content, not the whole message object
            inputs = {
                "input": last_user_message, 
                "metadata": {
                    "user_name": user_info['name'],
                    "user_id": user_info['id'],
                    "user_email": user_info['email'],
                    "chat_id": body.get('chat_id'),
                    "model": body.get('model'),
                },
            }
            
            self.run_id = uuid.uuid4()
            self.post_run(self.run_id, f"filter:{self.name}", "llm", inputs)
            
            return body

        except Exception as e:
            print(f"Error in inlet method: {e}")
            return body  # Return original body on error

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """Process outgoing response and update LangSmith trace."""
        print(f"outlet:{__name__}")

        try:
            messages = body.get("messages", [])  # Use the top-level "messages" list
            last_assistant_message = get_last_assistant_message(messages)
            
            if last_assistant_message is None:
                print("No valid assistant message found")
                return body

            # Ensure you're sending the message content, not the whole message object
            outputs = {
                "output": last_assistant_message,
                "model": body.get('model'),
            }

            if self.run_id is not None:
                self.patch_run(self.run_id.hex, outputs)
            
            return body

        except Exception as e:
            print(f"Error in outlet method: {e}")
            return body  # Return original body on error

    def post_run(
        self,
        run_id: uuid.UUID,
        name: str,
        run_type: str,
        inputs: Dict[str, Any],
        parent_id: Optional[uuid.UUID] = None,
    ):
        """Posts a new run to the LangSmith API."""
        try:
            data = {
                "id": run_id.hex,
                "name": name,
                "run_type": run_type,
                "inputs": inputs,
                "start_time": datetime.now(timezone.utc).isoformat(),
            }
            if parent_id:
                data["parent_run_id"] = parent_id.hex
            response = requests.post(
                f"{self.valves.api_url}/runs",
                json=data,
                headers={"x-api-key": self.valves.api_key},
            )
            response.raise_for_status()
            print(f"Run posted successfully: {data['id']}")
        except requests.RequestException as e:
            print(f"Error posting run: {e}")

    def patch_run(self, run_id: str, outputs: Dict[str, Any]):
        """Patches a run with outputs."""
        try:
            response = requests.patch(
                f"{self.valves.api_url}/runs/{run_id}",
                json={
                    "outputs": outputs,
                    "end_time": datetime.now(timezone.utc).isoformat(),
                },
                headers={"x-api-key": self.valves.api_key},
            )
            response.raise_for_status()
            print(f"Run patched successfully: {run_id}")
        except requests.RequestException as e:
            print(f"Error patching run: {e}")