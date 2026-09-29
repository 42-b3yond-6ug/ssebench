import os

import yaml

# The directory where individual model configuration files are stored.
models_dir = "/models"

# Base template for the final LiteLLM configuration.
BASE_TEMPLATE = """
model_list: []

general_settings:
  master_key: sk-12345

litellm_settings:
  request_timeout: 600
  set_verbose: False
  json_logs: True
  modify_params: True
  drop_params: True
"""

# Load the base template structure into a Python dictionary.
config_data = yaml.safe_load(BASE_TEMPLATE)

# A list to hold all the individual model configurations.
aggregated_models = []

# Check if the models directory exists to prevent errors.
if os.path.isdir(models_dir):
    # Iterate over each file in the specified directory.
    for filename in sorted(os.listdir(models_dir)):
        # Process only files with .yaml or .yml extensions.
        if filename.endswith((".yaml", ".yml")):
            filepath = os.path.join(models_dir, filename)
            with open(filepath) as f:
                try:
                    # Parse the YAML content of the model file.
                    # This is expected to be a list of model definitions.
                    model_config = yaml.safe_load(f)
                    if isinstance(model_config, list):
                        # Add the model(s) from the file to our aggregate list.
                        aggregated_models.extend(model_config)
                except yaml.YAMLError:
                    # Silently ignore malformed YAML files or log to stderr.
                    # For piping, it's best to avoid printing errors to stdout.
                    # To see errors during debugging, you could uncomment the next line:
                    # sys.stderr.write(f"Warning: Skipping malformed file {filename}: {e}\n")
                    pass

# Inject the complete list of models into the main configuration dictionary.
config_data["model_list"] = aggregated_models

# Convert the final Python dictionary back into a YAML formatted string.
# The output is clean, without any extra text, for direct piping.
final_yaml_output = yaml.dump(config_data, sort_keys=False, indent=2)

# Print the final raw YAML content to standard output.
print(final_yaml_output)
