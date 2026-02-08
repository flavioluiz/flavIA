"""Recursive agent with parallel execution for flavIA."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from flavia.config import Settings

from .base import BaseAgent
from .profile import AgentProfile


class RecursiveAgent(BaseAgent):
    """Agent capable of spawning and managing sub-agents."""

    MAX_ITERATIONS = 20

    def __init__(
        self,
        settings: Settings,
        profile: AgentProfile,
        agent_id: str = "main",
        depth: int = 0,
        parent_id: Optional[str] = None,
    ):
        super().__init__(settings, profile, agent_id, depth, parent_id)
        self._child_counter = 0
        self._active_children: dict[str, "RecursiveAgent"] = {}

    def run(self, user_message: str) -> str:
        """Run the agent with a user message."""
        self.messages.append({"role": "user", "content": user_message})

        iterations = 0
        pending_spawns: list[dict[str, Any]] = []

        while iterations < self.MAX_ITERATIONS:
            iterations += 1

            response = self._call_llm(self.messages)
            self.messages.append(self._assistant_message_to_dict(response))

            if not response.tool_calls:
                return response.content or ""

            tool_results, spawns = self._process_tool_calls_with_spawns(response.tool_calls)
            self.messages.extend(tool_results)
            pending_spawns.extend(spawns)

            if pending_spawns:
                spawn_results = self._execute_spawns_parallel(pending_spawns)

                for spawn_result in spawn_results:
                    tool_call_id = spawn_result["tool_call_id"]
                    for msg in self.messages:
                        if msg.get("tool_call_id") == tool_call_id:
                            msg["content"] = spawn_result["content"]
                            break

                pending_spawns = []

        self.log("Max iterations reached")
        return "Maximum iterations reached. Please try a more specific request."

    def _process_tool_calls_with_spawns(
        self,
        tool_calls: list[Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Process tool calls and identify spawn requests."""
        results = []
        spawns = []

        for tool_call in tool_calls:
            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            self.log(f"Tool: {name}({args})")

            result = self._execute_tool(name, args)

            if result.startswith("__SPAWN_AGENT__:"):
                spawn_info = self._parse_spawn_agent(result, args)
                spawn_info["tool_call_id"] = tool_call.id
                spawns.append(spawn_info)
                result = "[Spawning sub-agent...]"

            elif result.startswith("__SPAWN_PREDEFINED__:"):
                spawn_info = self._parse_spawn_predefined(result, args)
                spawn_info["tool_call_id"] = tool_call.id
                spawns.append(spawn_info)
                result = "[Spawning predefined agent...]"

            results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        return results, spawns

    def _parse_spawn_agent(self, result: str, args: dict) -> dict[str, Any]:
        """Parse spawn_agent result into spawn request."""
        _, data = result.split(":", 1)
        payload = self._parse_spawn_payload(data)

        if payload is not None:
            task = payload.get("task", args.get("task", ""))
            context = payload.get("context", args.get("context", ""))
            model = payload.get("model")
            tools = payload.get("tools")
            if tools is not None and not isinstance(tools, list):
                tools = None
        else:
            # Backward-compatible parsing for older delimiter payloads.
            parts = data.split("|")
            task = parts[0] if len(parts) > 0 else args.get("task", "")
            context = parts[1] if len(parts) > 1 else args.get("context", "")
            model = parts[2] if len(parts) > 2 and parts[2] else None
            tools_str = parts[3] if len(parts) > 3 else ""
            tools = [t.strip() for t in tools_str.split(",") if t.strip()] if tools_str else None

        return {
            "type": "dynamic",
            "task": task,
            "context": context,
            "model": model,
            "tools": tools,
        }

    def _parse_spawn_predefined(self, result: str, args: dict) -> dict[str, Any]:
        """Parse spawn_predefined_agent result into spawn request."""
        _, data = result.split(":", 1)
        payload = self._parse_spawn_payload(data)
        if payload is not None:
            agent_name = payload.get("agent_name", args.get("agent_name", ""))
            task = payload.get("task", args.get("task", ""))
        else:
            # Backward-compatible parsing for older delimiter payloads.
            parts = data.split("|")
            agent_name = parts[0] if len(parts) > 0 else args.get("agent_name", "")
            task = parts[1] if len(parts) > 1 else args.get("task", "")

        return {
            "type": "predefined",
            "agent_name": agent_name,
            "task": task,
        }

    def _parse_spawn_payload(self, data: str) -> Optional[dict[str, Any]]:
        """Parse JSON payload used by spawn tools."""
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _execute_spawns_parallel(self, spawns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute spawn requests in parallel."""
        if not spawns:
            return []

        results = []
        workers = min(len(spawns), self.settings.parallel_workers)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}

            for spawn in spawns:
                future = executor.submit(self._execute_single_spawn, spawn)
                futures[future] = spawn["tool_call_id"]

            for future in as_completed(futures):
                tool_call_id = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = f"Error in sub-agent: {e}"

                results.append({
                    "tool_call_id": tool_call_id,
                    "content": result,
                })

        return results

    def _execute_single_spawn(self, spawn: dict[str, Any]) -> str:
        """Execute a single spawn request."""
        if spawn["type"] == "predefined":
            return self._spawn_predefined(spawn["agent_name"], spawn["task"])
        else:
            return self._spawn_dynamic(
                spawn["task"],
                spawn["context"],
                spawn.get("model"),
                spawn.get("tools"),
            )

    def _spawn_predefined(self, agent_name: str, task: str) -> str:
        """Spawn a predefined sub-agent."""
        subagent_profile = self.profile.create_subagent_profile(agent_name)
        if not subagent_profile:
            return f"Error: Unknown predefined agent '{agent_name}'"

        self._child_counter += 1
        child_id = f"{self.context.agent_id}.{agent_name}.{self._child_counter}"

        self.log(f"Spawning predefined agent: {agent_name} as {child_id}")

        child = RecursiveAgent(
            settings=self.settings,
            profile=subagent_profile,
            agent_id=child_id,
            depth=self.context.current_depth + 1,
            parent_id=self.context.agent_id,
        )

        try:
            result = child.run(task)
            return f"[{agent_name}]: {result}"
        except Exception as e:
            return f"Error in {agent_name}: {e}"

    def _spawn_dynamic(
        self,
        task: str,
        context: str,
        model: Optional[str] = None,
        tools: Optional[list[str]] = None,
    ) -> str:
        """Spawn a dynamic sub-agent."""
        self._child_counter += 1
        child_id = f"{self.context.agent_id}.sub.{self._child_counter}"

        self.log(f"Spawning dynamic agent: {child_id}")

        profile = AgentProfile(
            context=context,
            model=model or self.profile.model,
            base_dir=self.profile.base_dir,
            tools=tools or self.profile.tools,
            subagents={},
            name=f"sub-{self._child_counter}",
            max_depth=self.profile.max_depth,
        )

        child = RecursiveAgent(
            settings=self.settings,
            profile=profile,
            agent_id=child_id,
            depth=self.context.current_depth + 1,
            parent_id=self.context.agent_id,
        )

        try:
            result = child.run(task)
            return f"[sub-agent]: {result}"
        except Exception as e:
            return f"Error in sub-agent: {e}"
