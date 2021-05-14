from datetime import datetime, time, timedelta
from uuid import UUID
from typing import List, Set, Optional
from enum import Enum
from fastapi import FastAPI, Query, Path, Body, Cookie, Header, Form, File, UploadFile, \
    HTTPException, Request, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, HttpUrl, EmailStr
from jose import JWTError, jwt
from passlib.context import CryptContext


class UserIn(BaseModel):
    username: str
    password: str
    email: EmailStr
    full_name: Optional[str] = None


class UserOut(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None


class Image(BaseModel):
    url: HttpUrl
    name: str


class Item(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    tax: float = 10.5
    tags: List[str] = []


class Offer(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    items: List[Item]


class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None


class UserInDB(User):
    hashed_password: str


class ModelName(str, Enum):
    alexnet = 'alexnet'
    resnet = 'resnet'
    lenet = 'lenet'


class UnicornException(Exception):
    def __init__(self, name: str):
        self.name = name


class CommonQueryParams:
    def __init__(self, q: Optional[str] = None, skip: int = 0, limit: int = 100):
        self.q = q
        self.skip = skip
        self.limit = limit


def query_extractor(q: Optional[str] = None):
    return q


def query_or_cookie_extractor(
        q: str = Depends(query_extractor), last_query: Optional[str] = Cookie(None)
):
    if not q:
        return last_query
    return q


async def verify_token(x_token: str = Header(...)):
    if x_token != "fake-super-secret-token":
        raise HTTPException(status_code=400, detail="X-Token header invalid")


async def verify_key(x_key: str = Header(...)):
    if x_key != "fake-super-secret-key":
        raise HTTPException(status_code=400, detail="X-Key header invalid")
    return x_key


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


fake_items_db = [{"item_name": "Foo"}, {"item_name": "Bar"}, {"item_name": "Baz"}]

fake_db = {}

# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


fake_users_db = {
    "johndoe": {
        "username": "johndoe",
        "full_name": "John Doe",
        "email": "johndoe@example.com",
        "hashed_password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",
        "disabled": False,
    }
}

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None

items = {
    "foo": {"name": "Foo", "price": 50.2},
    "bar": {"name": "Bar", "description": "The bartenders", "price": 62, "tax": 20.2},
    "baz": {"name": "Baz", "description": None, "price": 50.2, "tax": 10.5, "tags": []},
}


def fake_decode_token(token):
    # This doesn't provide any security at all
    # Check the next version
    user = get_user(fake_users_db, token)
    return user


def fake_hash_password(password: str):
    return "fakehashed" + password


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user_dict = fake_users_db.get(form_data.username)
    if not user_dict:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    user = UserInDB(**user_dict)
    hashed_password = fake_hash_password(form_data.password)
    if not hashed_password == user.hashed_password:
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    return {"access_token": user.username, "token_type": "bearer"}


# @app.exception_handler(UnicornException)
# async def unicorn_exception_handler(request: Request, exc: UnicornException):
#     return JSONResponse(
#         status_code=418,
#         content={"message": f"Oops! {exc.name} did something. There goes a rainbow..."},
#     )
#
# @app.get("/unicorns/{name}")
# async def read_unicorn(name: str):
#     if name == "yolo":
#         raise UnicornException(name=name)
#     return {"unicorn_name": name}
#
# @app.get(
#     "/items/{item_id}/name",
#     response_model=Item,
#     response_model_include={"name", "description"},
# )
# async def read_item_name(item_id: str):
#     return items[item_id]
#
# @app.get("/items/{item_id}/public", response_model=Item, response_model_exclude={"tax"})
# async def read_item_public_data(item_id: str):
#     return items[item_id]
#
# @app.get("/items/{item_id}")
# async def read_item(item_id: str):
#     if item_id not in items:
#         raise HTTPException(status_code=404, detail="Item not found")
#     return {"item": items[item_id]}
#
# @app.get("/items/")
# async def read_items(ads_id: Optional[str] = Cookie(None), user_agent: Optional[str] = Header(None)):
#     return {"ads_id": ads_id, "User-Agent": user_agent}
#
# @app.post(
#     "/items/",
#     response_model=Item,
#     summary="Create an item",
#     response_description="The created item",
#     status_code=status.HTTP_201_CREATED,
#     tags=["items"]
# )
# async def create_item(item: Item):
#     """
#         Create an item with all the information:
#
#         - **name**: each item must have a name
#         - **description**: a long description
#         - **price**: required
#         - **tax**: if the item doesn't have tax, you can omit this
#         - **tags**: a set of unique tag strings for this item
#     """
#     return item
#
# @app.get("/items/user/{item_id}")
# async def read_user_item(item_id: str, needy: str):
#     item = {"item_id": item_id, "needy": needy}
#     return item
#
# @app.get("/items/{item_id}")
# async def read_items(
#     q: str, item_id: int = Path(..., title="The ID of the item to get", gt=0, le=1000)
# ):
#     results = {"item_id": item_id}
#     if q:
#         results.update({"q": q})
#     return results
#
# @app.put("/items/{item_id}")
# async def read_items(
#     item_id: UUID,
#     start_datetime: Optional[datetime] = Body(None),
#     end_datetime: Optional[datetime] = Body(None),
#     repeat_at: Optional[time] = Body(None),
#     process_after: Optional[timedelta] = Body(None),
# ):
#     start_process = start_datetime + process_after
#     duration = end_datetime - start_process
#     return {
#         "item_id": item_id,
#         "start_datetime": start_datetime,
#         "end_datetime": end_datetime,
#         "repeat_at": repeat_at,
#         "process_after": process_after,
#         "start_process": start_process,
#         "duration": duration,
#     }
#
# @app.get("/users/me")
# async def read_user_me():
#     return {"user_id": "the current user"}
#
#
# @app.get("/users/{user_id}")
# async def read_user(user_id: str):
#     return {"user_id": user_id}
#
# @app.get("/users/{user_id}/items/{item_id}")
# async def read_user_item(user_id: int, item_id: str, q: Optional[str] = None, short: bool = False):
#     item = {"item_id": item_id, "owner_id": user_id}
#     if q:
#         item.update({"q": q})
#     if not short:
#         item.update({"description": "This is an amazing item that has a long description"})
#     return item
#
# @app.get("/models/{model_name}")
# async def get_model(model_name: ModelName):
#     if model_name == ModelName.alexnet:
#         return {"model_name": model_name, "message": "Deep Learning FTW!"}
#     if model_name.value == 'lenet':
#         return {"model_name": model_name, "message": "LeCNN all the images"}
#
#     return {"model_name": model_name, "message": "Have some residuals"}
#
# @app.get("/files/{file_path:path}")
# async def read_file(file_path: str):
#     return {"file_path": file_path}
#
# @app.post("/images/multiple/")
# async def create_multiple_images(images: List[Image]):
#     return images
#
# # Don't do this in production!
# @app.post("/user/", response_model=UserOut)
# async def create_user(user: UserIn):
#     return user
#
# @app.post("/login/")
# async def login(username: str = Form(...), password: str = Form(...)):
#     return {"username": username}
#
#
# @app.post("/files/")
# async def create_files(file: bytes = File(...), fileb: UploadFile = File(...), token: str = Form(...)):
#     return {
#         "file_size": len(file),
#         "token": token,
#         "fileb_content_type": fileb.content_type,
#     }
#
# @app.post("/uploadfiles")
# async def create_upload_files(files: List[UploadFile] = File(...)):
#     return {"filenames": [file.filename for file in files]}
#
# @app.get("/")
# async def main():
#     content = """
# <body>
# <form action="/files/" enctype="multipart/form-data" method="post">
# <input name="files" type="file" multiple>
# <input type="submit">
# </form>
# <form action="/uploadfiles/" enctype="multipart/form-data" method="post">
# <input name="files" type="file" multiple>
# <input type="submit">
# </form>
# </body>
#     """
#     return HTMLResponse(content=content)

@app.get("/items/{item_id}", response_model=Item)
async def read_item(item_id: str):
    return items[item_id]


@app.patch("/items/{item_id}", response_model=Item)
async def update_item(item_id: str, item: Item):
    stored_item_data = items[item_id]
    stored_item_model = Item(**stored_item_data)
    update_data = item.dict(exclude_unset=True)
    updated_item = stored_item_model.copy(update=update_data)
    items[item_id] = jsonable_encoder(updated_item)
    return updated_item


# @app.get("/items/")
# async def read_items(commons: CommonQueryParams = Depends()):
#     response = {}
#     if commons.q:
#         response.update({"q": commons.q})
#     items = fake_items_db[commons.skip : commons.skip + commons.limit]
#     response.update({"items": items})
#     return response


@app.get("/items/")
async def read_query(query_or_default: str = Depends(query_or_cookie_extractor)):
    return {"q_or_cookie": query_or_default}


@app.get("/items/", dependencies=[Depends(verify_token), Depends(verify_key)])
async def read_items():
    return [{"item": "Foo"}, {"item": "Bar"}]


@app.get("/users/me")
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user
