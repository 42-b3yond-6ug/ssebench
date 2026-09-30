# Initialize the model selected by the user
# It will check if the model exists in LiteLLM,
# then use the /key/generate API to generate a new key with strict limit.

import difflib
from typing import final

import httpx
import yaml
from pydantic import BaseModel

from ssebench import paths, settings, stack
from ssebench.backends import ProxyEndpoint
from ssebench.errors import UserError

MAX_BUDGET = 10

# The model name of a run that makes no model calls.
NO_MODEL = "none"


class ModelError(UserError):
    """The model is unknown, or the LiteLLM proxy cannot provide it."""


def model_names() -> set[str]:
    """The names of the models that `models/*.yaml` define."""
    names: set[str] = set()
    for path in sorted(paths.models_dir().glob("*.y*ml")):
        try:
            entries = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        if isinstance(entries, list):
            names.update(str(e["model_name"]) for e in entries if isinstance(e, dict) and "model_name" in e)
    return names


def unknown_model(model: str, defined: set[str]) -> ModelError:
    """The error for a model that is not among the `defined` ones, listing them."""
    known = sorted(defined)
    message = f"Unknown model {model!r}"
    if close := difflib.get_close_matches(model, known, n=1):
        message += f" (did you mean {close[0]!r}?)"
    return ModelError(f"{message}. Available models: {', '.join(known)}." if known else f"{message}.")


def require_defined(model: str) -> None:
    """Fail before anything starts when `models/*.yaml` define models and `model` is not one of them.

    Raises:
        ModelError: With the models that are defined.
    """
    defined = model_names()
    if defined and model not in defined:
        raise unknown_model(model, defined)


class UserCreateResult(BaseModel):
    user_id: str
    key: str


class UserInfo(BaseModel):
    spend: float


class UserInfoResult(BaseModel):
    user_id: str
    user_info: UserInfo


@final
class Model:
    def __init__(self, model: str, proxy: ProxyEndpoint | None = None):
        """`proxy` names the LiteLLM proxy of a backend that has its own; the default is the local Compose stack."""
        self.model_name = model
        self.host_url = proxy.host_url if proxy else stack.host_url()
        self.service_url = proxy.service_url if proxy else stack.service_url()

        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {settings.litellm_master_key()}",
                "Accept": "application/json",
            }
        )

        try:
            if self.check_existence() is False:
                defined = model_names()
                if model in defined:
                    raise ModelError(
                        f"The LiteLLM proxy at {self.host_url} does not serve model {model!r}, although "
                        "models/*.yaml define it; restart the proxy with `ssebench proxy up`"
                    )
                raise unknown_model(model, defined)
            self.create_user()
        except httpx.HTTPError as e:
            raise ModelError(f"Cannot use the LiteLLM proxy at {self.host_url}: {e}") from e

    def check_existence(self) -> bool:
        url = f"{self.host_url}/models/{self.model_name}"
        response = self.client.get(url)
        return response.status_code == 200

    def create_user(self):
        """
        Create a user in LiteLLM.
        This will also create a key for the user.
        """
        url = f"{self.host_url}/user/new"

        data = {
            "models": [self.model_name],
            "max_budget": MAX_BUDGET,
        }
        response = self.client.post(url, json=data).raise_for_status()
        user_result = UserCreateResult.model_validate_json(response.text)

        self.user_id = user_result.user_id
        self.api_key = user_result.key

    def get_spend(self) -> float:
        """
        Get total spend of the user.
        Since we use differernt users for different task, the usage of user is essentially the usage of task.
        """
        url = f"{self.host_url}/user/info"
        response = self.client.get(url, params={"user_id": self.user_id})
        user_result = UserInfoResult.model_validate_json(response.text)
        spend = user_result.user_info.spend
        return spend


@final
class NoModel:
    """Stands in for the model of a run that makes no model calls, such as a reference run.

    It has no proxy key and no spend, so the run needs no provider key.
    """

    model_name: str = NO_MODEL
    api_key: str = ""
    service_url: str = ""

    def get_spend(self) -> float:
        return 0.0
