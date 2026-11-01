import { createOpenAICompatible } from "@ai-sdk/openai-compatible";

const MODEL_ENVIRONMENT_VARIABLES = [
  "OUBLIAI_MODEL_BASE_URL",
  "OUBLIAI_MODEL_API_KEY",
  "OUBLIAI_MODEL_ID",
] as const;

type ModelEnvironmentVariable = (typeof MODEL_ENVIRONMENT_VARIABLES)[number];
type ModelEnvironment = Readonly<Partial<Record<ModelEnvironmentVariable, string>>>;

export class ModelNotConfiguredError extends Error {
  readonly missing: readonly ModelEnvironmentVariable[];

  constructor(missing: readonly ModelEnvironmentVariable[]) {
    super(`Missing model environment variables: ${missing.join(", ")}`);
    this.name = "ModelNotConfiguredError";
    this.missing = missing;
  }
}

function configuredValue(
  environment: ModelEnvironment,
  variable: ModelEnvironmentVariable,
): string | undefined {
  const value = environment[variable]?.trim();
  return value === "" ? undefined : value;
}

export function createModel(environment: ModelEnvironment = process.env) {
  const missing = MODEL_ENVIRONMENT_VARIABLES.filter(
    (variable) => configuredValue(environment, variable) === undefined,
  );
  if (missing.length > 0) throw new ModelNotConfiguredError(missing);

  const baseURL = configuredValue(environment, "OUBLIAI_MODEL_BASE_URL");
  const apiKey = configuredValue(environment, "OUBLIAI_MODEL_API_KEY");
  const modelId = configuredValue(environment, "OUBLIAI_MODEL_ID");
  if (baseURL === undefined || apiKey === undefined || modelId === undefined) {
    throw new ModelNotConfiguredError(missing);
  }

  return createOpenAICompatible({
    name: "oubliai-model",
    baseURL,
    apiKey,
  })(modelId);
}
