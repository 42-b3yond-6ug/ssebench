# Initialize the model selected by the user
# It will check if the model exists in LiteLLM,
# then use the /key/generate API to generate a new key with strict limit.

from typing import final

import httpx
from pydantic import BaseModel

from ssebench import settings, stack

MAX_BUDGET = 10


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
    def __init__(self, model: str):
        self.model_name = model
        self.host_url = stack.host_url()
        self.service_url = stack.service_url()

        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {settings.litellm_master_key()}",
                "Accept": "application/json",
            }
        )

        if self.check_existence() is False:
            raise ValueError(f"Model {model} does not exist.")

        self.create_user()

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
