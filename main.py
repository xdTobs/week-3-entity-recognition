import base64
import os
import re
import asyncio

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel

load_dotenv()

API_BASE_URL = "https://api.campusai.compute.dtu.dk/v1"
MODEL = "cai-instant"
# CampusAI limits to 8 active requests, aquire the semaphore to make a request
campusai_slots = asyncio.Semaphore(8)

app = FastAPI(title="Extract persons API")


class PersonsResponse(BaseModel):
    persons: list[str]


class PersonsRequest(BaseModel):
    text: str


@app.post("/v1/extract-persons", response_model=PersonsResponse)
async def extract_sentences(request: PersonsRequest) -> PersonsResponse:
    """Extract entities from text"""
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY is not configured")

    client = AsyncOpenAI(api_key=api_key, base_url=API_BASE_URL, timeout=30.0, max_retries=2)
    try:
        async with campusai_slots:
            response = await client.chat.completions.parse(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "Extract person names from the provided text. Return an empty persons list if no people are mentioned."},
                    {"role": "user", "content": request.text},
                ],
                temperature=0,
                max_tokens=1024,
                response_format=PersonsResponse,
            )
    except OpenAIError as error:
        raise RuntimeError("CampusAI request failed") from error
    finally:
        await client.close()

    if not response.choices or response.choices[0].message.parsed is None:
        raise HTTPException(status_code=502, detail="CampusAI did not return a persons response")

    return response.choices[0].message.parsed
