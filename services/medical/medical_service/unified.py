"""Production entrypoint: both models in one process on one HTTP port."""

from .app import create_app
from .config import Settings, TeachingSettings, shared_api_key_variable

key_variable = shared_api_key_variable()
app = create_app(
    Settings.from_env(api_key_variable=key_variable),
    teaching_settings=TeachingSettings.from_env(api_key_variable=key_variable),
    require_teaching=True,
)
