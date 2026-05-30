from jinja2 import Template
from typing import Dict, Any
from .provider import get_ai_provider
from .models import AiGeneration, PromptTemplate
from .prompts.prompt_blueprints import EXECUTABLE_GENERATION_SYSTEM_PROMPT

class DocumentGenerationEngine:
    """
    Compiles raw parameters into structured legal content by executing 
    Jinja2 prompt blueprints against model provider targets.
    """
    def __init__(self, generation_instance: AiGeneration):
        self.generation = generation_instance

    def compile_document(self) -> str:
        template_record: PromptTemplate = self.generation.template
        
        # Hydrate variables into the target Jinja template string
        jinja_compiled_blueprint = Template(template_record.user_prompt)
        hydrated_user_prompt = jinja_compiled_blueprint.render(**self.generation.input_fields)

        # Merge system operational instructions cleanly
        comprehensive_system_instructions = (
            f"{template_record.system_prompt}\n\n{EXECUTABLE_GENERATION_SYSTEM_PROMPT}"
        )

        ai_engine = get_ai_provider(model_name=self.generation.model_used)
        execution_outcome = ai_engine.generate_response(
            system_prompt=comprehensive_system_instructions,
            user_prompt=hydrated_user_prompt,
            temperature=0.2  # Slight variance for professional vocabulary expansion
        )

        # Update core generative context attributes
        self.generation.generated_content = execution_outcome["content"]
        self.generation.tokens_used = execution_outcome["tokens_used"]
        self.generation.save()

        return execution_outcome["content"]