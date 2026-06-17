from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, validator
import uvicorn
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define routers and app
scene_operations_router = APIRouter()
scene_generation_app = FastAPI()

class SceneDimensionsModel(BaseModel):
    width: int
    height: int
    object_list: list

class SceneDataModel(BaseModel):
    scene_dimensions: SceneDimensionsModel

    @validator('scene_dimensions', pre=True)
    def validate_scene_dimensions(cls, dimensions_value):
        if not isinstance(dimensions_value, dict):
            logger.error('Scene dimensions must be a dictionary.')
            raise ValueError('Scene dimensions must be a dictionary.')
        required_keys = {"width", "height", "object_list"}
        missing_keys = required_keys - set(dimensions_value.keys())
        if missing_keys:
            logger.error(f'Missing required keys: {", ".join(missing_keys)}')
            raise ValueError(f'Missing required keys: {", ".join(missing_keys)}')
        return dimensions_value

def process_scene_details(scene_data_model: SceneDataModel) -> dict:
    logger.info("Processing scene details.")
    scene_dimensions_dict = scene_data_model.scene_dimensions.dict()
    scene_dimensions_dict["is_procedural"] = True
    return scene_dimensions_dict

@scene_operations_router.post("/generate")
async def generate_scene(scene_data_input: SceneDataModel):
    try:
        logger.info("Generating scene.")
        processed_scene_data = process_scene_details(scene_data_input)
        return {"generated_scene": processed_scene_data}
    except ValueError as value_error:
        logger.error(f"Value error in generating scene: {str(value_error)}")
        raise HTTPException(status_code=422, detail=str(value_error))
    except Exception as general_exception:
        logger.error(f"Error in generating scene: {str(general_exception)}")
        raise HTTPException(status_code=500, detail=str(general_exception))

@scene_operations_router.get("/health")
def check_service_health():
    logger.info("Health check requested.")
    return {"status": "operational", "service": "SceneGenerationService"}

@scene_generation_app.on_event("startup")
async def on_application_startup():
    logger.info("Application start-up event.")

@scene_generation_app.on_event("shutdown")
async def on_application_shutdown():
    logger.info("Application shut-down event.")

scene_generation_app.include_router(scene_operations_router)

if __name__ == "__main__":
    logger.info("Starting the application.")
    uvicorn.run(scene_generation_app, host="0.0.0.0", port=9001)