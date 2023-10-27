import os
from typing import Dict, Optional, List
from dataclasses import dataclass

import cattrs
import yaml

from helm.common.hierarchical_logger import hlog
from helm.common.object_spec import ObjectSpec
from helm.benchmark.model_metadata_registry import (
    ModelMetadata,
    ALL_MODELS_METADATA,
    MODEL_NAME_TO_MODEL_METADATA,
    get_model_metadata,
    TEXT_MODEL_TAG,
    FULL_FUNCTIONALITY_TEXT_MODEL_TAG,
)

from toolbox.printing import print_visible, debug  # TODO(PR): Remove this


MODEL_DEPLOYMENTS_FILE = "model_deployments.yaml"


class ClientSpec(ObjectSpec):
    pass


class WindowServiceSpec(ObjectSpec):
    pass


@dataclass(frozen=True)
class ModelDeployment:
    """A model deployment is an accessible instance of this model (e.g. a hosted endpoint).

    A model can have multiple model deployments."""

    # Name of the model deployment.
    # Usually formatted as "<hosting_group>/<engine_name>"
    # Example: "huggingface/t5-11b"
    name: str

    # Specification for instantiating the client for this model deployment.
    client_spec: ClientSpec

    # Name of the model that this model deployment is for.
    # Refers to the field "name" in the Model class.
    # If unset, defaults to the same value as `name`.
    model_name: Optional[str] = None

    # Tokenizer for this model deployment.
    # If unset, auto-inferred by the WindowService.
    tokenizer_name: Optional[str] = None

    # Specification for instantiating the window service for this model deployment.
    window_service_spec: Optional[WindowServiceSpec] = None

    # Maximum sequence length for this model deployment.
    max_sequence_length: Optional[int] = None

    # Maximum request length for this model deployment.
    # If unset, defaults to the same value as max_sequence_length.
    max_request_length: Optional[int] = None

    @property
    def host_group(self) -> str:
        """
        Extracts the host group from the model deployment name.
        Example: "huggingface" from "huggingface/t5-11b"
        This can be different from the creator organization (for example "together")
        """
        return self.name.split("/")[0]

    @property
    def engine(self) -> str:
        """
        Extracts the model engine from the model deployment name.
        Example: 'ai21/j1-jumbo' => 'j1-jumbo'
        """
        return self.name.split("/")[1]


@dataclass(frozen=True)
class ModelDeployments:
    model_deployments: List[ModelDeployment]


ALL_MODEL_DEPLOYMENTS: List[ModelDeployment] = [
    # ModelDeployment(
    #     name="anthropic/claude-v1.3",
    #     tokenizer_name="anthropic/claude",
    #     client_spec=ClientSpec(
    #         class_name="helm.proxy.clients.anthropic_client.AnthropicClient",
    #         args={},  # api_key should be auto-filled
    #     ),
    #     window_service_spec=WindowServiceSpec(
    #         class_name="helm.benchmark.window_services.anthropic_window_service.AnthropicWindowService",
    #         args={},  # No args
    #     ),
    # ),
]

DEPLOYMENT_NAME_TO_MODEL_DEPLOYMENT: Dict[str, ModelDeployment] = {
    deployment.name: deployment for deployment in ALL_MODEL_DEPLOYMENTS
}


# ===================== REGISTRATION FUNCTIONS ==================== #
def register_model_deployment(model_deployment: ModelDeployment) -> None:
    hlog(f"Registered model deployment {model_deployment.name}")
    DEPLOYMENT_NAME_TO_MODEL_DEPLOYMENT[model_deployment.name] = model_deployment

    model_name: str = model_deployment.model_name or model_deployment.name
    print_visible("register_model_deployment")
    debug(model_name, visible=True)

    try:
        model_metadata: ModelMetadata = get_model_metadata(model_name)
        deployment_names: List[str] = model_metadata.deployment_names or [model_metadata.name]
        if model_deployment.name not in deployment_names:
            if model_metadata.deployment_names is None:
                model_metadata.deployment_names = []
            model_metadata.deployment_names.append(model_deployment.name)
    except ValueError:
        # No model metadata exists for this model name.
        # Register a default model metadata.
        model_metadata = ModelMetadata(
            name=model_name,
            display_name=model_name,
            description="",
            access="limited",
            num_parameters=-1,
            release_date="unknown",
            tags=[TEXT_MODEL_TAG, FULL_FUNCTIONALITY_TEXT_MODEL_TAG],
            deployment_names=[model_deployment.name],
        )
        ALL_MODELS_METADATA.append(model_metadata)
        MODEL_NAME_TO_MODEL_METADATA[model_name] = model_metadata
        hlog(f"Registered default metadata for model {model_name}")


def register_model_deployments_from_path(path: str) -> None:
    hlog(f"Reading model deployments from {path}...")
    print_visible("register_model_deployments_from_path")
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    model_deployments: ModelDeployments = cattrs.structure(raw, ModelDeployments)
    for model_deployment in model_deployments.model_deployments:
        debug(model_deployment, visible=True)
        register_model_deployment(model_deployment)


def maybe_register_model_deployments_from_base_path(base_path: str) -> None:
    """Register model deployments from prod_env/model_deployments.yaml"""
    print_visible("maybe_register_model_deployments_from_base_path")
    path = os.path.join(base_path, MODEL_DEPLOYMENTS_FILE)
    if os.path.exists(path):
        register_model_deployments_from_path(path)


# ===================== UTIL FUNCTIONS ==================== #
def get_model_deployment(name: str) -> ModelDeployment:
    if name not in DEPLOYMENT_NAME_TO_MODEL_DEPLOYMENT:
        raise ValueError(f"Model deployment {name} not found")
    return DEPLOYMENT_NAME_TO_MODEL_DEPLOYMENT[name]


def get_model_deployments_by_host_group(host_group: str) -> List[str]:
    """
    Gets models by host group.
    Example:   together   =>   TODO(PR)
    """
    return [deployment.name for deployment in ALL_MODEL_DEPLOYMENTS if deployment.host_group == host_group]


def get_model_deployment_host_group(name: str) -> str:
    """
    Extracts the host group from the model deployment name.
    Example: "huggingface/t5-11b" => "huggingface"
    """
    deployment: ModelDeployment = get_model_deployment(name)
    return deployment.host_group


def get_default_deployment_for_model(model_metadata: ModelMetadata) -> ModelDeployment:
    """
    Given a model_metadata, returns the default model deployment.
    The default model deployment for a model is either the deployment
    with the same name as the model, or the first deployment for that model.

    TODO: Make this logic more complex.
    For example if several deplyments are available but only some can be used
    given the API keys present, then we should choose the one that can be used.
    """
    if model_metadata.name in DEPLOYMENT_NAME_TO_MODEL_DEPLOYMENT:
        return DEPLOYMENT_NAME_TO_MODEL_DEPLOYMENT[model_metadata.name]
    elif model_metadata.deployment_names is not None and len(model_metadata.deployment_names) > 0:
        deployment_name: str = model_metadata.deployment_names[0]
        if deployment_name in DEPLOYMENT_NAME_TO_MODEL_DEPLOYMENT:
            return DEPLOYMENT_NAME_TO_MODEL_DEPLOYMENT[deployment_name]
        raise ValueError(f"Model deployment {deployment_name} not found")
    raise ValueError(f"No default model deployment for model {model_metadata.name}")


def get_metadata_for_deployment(deployment_name: str) -> ModelMetadata:
    """
    Given a deployment name, returns the corresponding model metadata.
    """
    deployment: ModelDeployment = get_model_deployment(deployment_name)
    return get_model_metadata(deployment.model_name or deployment.name)
