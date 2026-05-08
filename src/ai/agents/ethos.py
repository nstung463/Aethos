"""Primary Ethos agent factory."""

from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from src.ai.permissions import PermissionContext
from src.ai.agents.subagents import DEFAULT_SUBAGENTS, build_task_tool
from src.ai.middleware import (
    EnvironmentMiddleware,
    MCPInstructionsMiddleware,
    MemoryMiddleware,
    NativeConnectionsMiddleware,
    SkillsMiddleware,
)
from src.ai.prompts.catalog import BASE_SYSTEM_PROMPT
from src.ai.skills import SkillRegistry
from src.ai.tools.filesystem.media_support import MediaBlockSupport
from src.backends.protocol import SandboxProtocol as FilesystemBackendProtocol
from src.app.services.storage_paths import StoragePathsService
from src.config import MCPServerSpec, get_mcp_servers, get_model, get_workspace
from src.logger import get_logger
from src.ai.tools.filesystem import build_filesystem_tools
from src.ai.tools.integrations import build_integration_tools
from src.ai.tools.mcp import MCPRuntime, build_mcp_tools
from src.ai.tools.orchestration import build_remember_tool, build_skill_tool
from src.ai.tools.shell import build_bash_tool, build_powershell_tool
from src.ai.tools.web import tavily_search, web_fetch_tool

logger = get_logger(__name__)


def _build_default_middleware(
    root_dir: str,
    mcp_servers: list[MCPServerSpec],
    model_name: str | None = None,
    skill_registry: SkillRegistry | None = None,
    owner_user_id: str | None = None,
) -> list[AgentMiddleware]:
    """Create a fresh middleware stack for an Ethos agent instance.

    Execution order (before_agent / wrap_model_call):
      1. EnvironmentMiddleware      — cwd, git, date, platform, model, CLAUDE.md hierarchy
      2. MCPInstructionsMiddleware  — per-server MCP instructions (skipped when empty)
      3. SkillsMiddleware           — available skills list
      4. MemoryMiddleware           — AGENTS.md persistent context
    All sections are computed once on the first turn and cached via PrivateStateAttr.
    """
    return [
        EnvironmentMiddleware(root_dir=root_dir, model_name=model_name),
        MCPInstructionsMiddleware(servers=mcp_servers),
        NativeConnectionsMiddleware(root_dir=root_dir, owner_user_id=owner_user_id),
        SkillsMiddleware(registry=skill_registry, root_dir=root_dir),
        MemoryMiddleware(
            agents_md_path=f"{root_dir}/AGENTS.md",
            auto_memory_path=str(StoragePathsService().memory_file(root_dir)),
        ),
    ]


def create_ethos_agent(
    root_dir: str | None = None,
    backend: FilesystemBackendProtocol | None = None,
    model: BaseChatModel | None = None,
    permission_context: PermissionContext | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    media_block_support: MediaBlockSupport | None = None,
    owner_user_id: str | None = None,
) -> object:
    """Create and return a compiled Ethos agent."""
    raw_backend_root = getattr(backend, "root", None) if backend is not None else None
    if root_dir is None:
        backend_root = raw_backend_root
        if isinstance(backend_root, Path):
            root_dir = str(backend_root.resolve())
        elif isinstance(backend_root, str) and backend_root.strip():
            root_dir = backend_root.strip()
        else:
            root_dir = get_workspace()
    if model is None:
        model = get_model()
    logger.info("Creating Ethos agent (backend=%s, workspace=%s)", "sandbox" if backend else "local", root_dir)

    mcp_servers = get_mcp_servers(root_dir, owner_user_id=owner_user_id)
    fs_tools = build_filesystem_tools(
        root_dir=root_dir,
        backend=backend,
        permission_context=permission_context,
        media_block_support=media_block_support,
    )
    extra_tools = []
    if backend is not None:
        if "bash" in backend.supported_shells:
            extra_tools.append(build_bash_tool(backend, permission_context=permission_context))
        if "powershell" in backend.supported_shells:
            extra_tools.append(build_powershell_tool(backend, permission_context=permission_context))

    web_tools = [tavily_search, web_fetch_tool]
    integration_tools = build_integration_tools(
        root_dir=root_dir,
        owner_user_id=owner_user_id,
        permission_context=permission_context,
    )
    mcp_runtime = MCPRuntime(mcp_servers)
    mcp_tools = build_mcp_tools(mcp_servers, runtime=mcp_runtime, permission_context=permission_context)
    skill_registry = SkillRegistry(root_dir, mcp_runtime=mcp_runtime)
    skill_tool = build_skill_tool(skill_registry, permission_context=permission_context)
    remember_tool = build_remember_tool(root_dir)
    base_tools = fs_tools + extra_tools + web_tools + integration_tools + mcp_tools + [skill_tool, remember_tool]
    subagent_skill_registry = SkillRegistry(root_dir, mcp_runtime=mcp_runtime)
    subagent_skill_tool = build_skill_tool(subagent_skill_registry, permission_context=permission_context)
    subagent_remember_tool = build_remember_tool(root_dir)
    subagent_base_tools = fs_tools + extra_tools + web_tools + integration_tools + mcp_tools + [subagent_skill_tool, subagent_remember_tool]
    # task_tool = build_task_tool(
    #     model=model,
    #     subagents=DEFAULT_SUBAGENTS,
    #     base_tools=subagent_base_tools,
    #     default_middleware=_build_default_middleware(
    #         root_dir,
    #         mcp_servers,
    #         skill_registry=subagent_skill_registry,
    #     ),
    # )
    # all_tools = base_tools + [task_tool]
    all_tools = base_tools
    logger.debug("Agent tools prepared (count=%d)", len(all_tools))

    if checkpointer is None:
        checkpointer = MemorySaver()
    model_name: str | None = getattr(model, "model_name", None) or getattr(model, "model", None)
    middleware = _build_default_middleware(
        root_dir,
        mcp_servers,
        model_name=model_name,
        skill_registry=skill_registry,
        owner_user_id=owner_user_id,
    )
    return create_agent(
        model=model,
        tools=all_tools,
        system_prompt=BASE_SYSTEM_PROMPT,
        middleware=middleware,
        checkpointer=checkpointer,
        name="ethos",
    )
