import requests
import json
import os
import base64

from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException

load_dotenv()
app = FastAPI()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1/me/top/artists"
SCOPE = "user-top-read"

USER_DB = "users.json"
if not os.path.exists(USER_DB):
    with open(USER_DB, "w") as f:
        json.dump([], f)


class User(BaseModel):
    name: str
    email: str
    preferences: list[str]

def new_id():
    """
    Devuelve el próximo id disponible para un usuario.

    Lee la base de datos de usuarios y devuelve el id más alto + 1. Si la base de
    datos está vacía, devuelve 1.

    Returns:
        int: El nuevo id disponible.
    """
    with open(USER_DB, "r") as f:
        users = json.load(f)
        if users:
            return max(user["id"] for user in users) + 1
        return 1


@app.post("/user/create")
def create_user(user: User):
    """
    Crea un nuevo usuario en la base de datos.

    Args:
        user (User): Información del usuario a crear.

    Returns:
        dict: Un diccionario con un mensaje de confirmación y el id del usuario creado.

    Raises:
        HTTPException: Si el usuario ya existe en la base de datos.
    """
    user_id = new_id()
    user_dict = user.model_dump()
    user_dict["id"] = user_id

    with open(USER_DB, "r") as f:
        users = json.load(f)
        if any(existing_user["email"] == user.email for existing_user in users):
            raise HTTPException(
                status_code=409, detail="El usuario ya existe en el sistema."
            )
        users.append(user_dict)

    with open(USER_DB, "w") as f:
        json.dump(users, f)

    return {"message": "El usuario se ha creado correctamente", "id": user_id}


@app.get("/user/{user_id}")
def get_user(user_id: int):
    """
    Obtiene un usuario por su id.
    
    Args:
        user_id (int): Identificador único del usuario.
    
    Returns:
        User: El usuario con el id proporcionado.
    
    Raises:
        HTTPException: Si el usuario no existe en la base de datos.
    """
    with open(USER_DB, "r") as f:
        users = json.load(f)
        user = next((u for u in users if u["id"] == user_id), None)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return user


@app.get("/users")
def get_user_list():
    """
    Obtiene la lista de todos los usuarios.

    Returns:
        list: Una lista de diccionarios representando a cada usuario en la base de datos.
    """

    with open(USER_DB, "r") as f:
        users = json.load(f)
        return users


@app.put("/user/{user_id}")
def update_user(user_id: int, user: User):
    """
    Actualiza un usuario por su id.

    Args:
        user_id (int): El id del usuario a actualizar.
        user (User): Información del usuario a actualizar.

    Returns:
        dict: Un diccionario con un mensaje de confirmación.

    Raises:
        HTTPException: Si el usuario no existe en la base de datos.
    """
    with open(USER_DB, "r") as f:
        users = json.load(f)
        for i, u in enumerate(users):
            if u["id"] == user_id:
                updated_user = user.dict(
                    exclude_unset=True
                )  # Solo actualiza los campos proporcionados
                users[i].update(updated_user)
                with open(USER_DB, "w") as f:
                    json.dump(users, f)
                return {"message": "Usuario actualizado correctamente"}
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


@app.delete("/user/{user_id}")
def delete_user(user_id: int):
    """
    Elimina un usuario por su id.

    Args:
        user_id (int): El id del usuario a eliminar.

    Returns:
        dict: Un diccionario con un mensaje de confirmación.

    Raises:
        HTTPException: Si el usuario no existe en la base de datos.
    """
    with open(USER_DB, "r") as f:
        users = json.load(f)
        for i, u in enumerate(users):
            if u["id"] == user_id:
                del users[i]
                with open(USER_DB, "w") as f:
                    json.dump(users, f)
                return {"message": "Usuario eliminado correctamente"}
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


@app.get("/spotify/auth")
def spotify_auth():
    """
    Genera la URL para que el usuario autorice la aplicación.
    """
    auth_url = (
        f"{SPOTIFY_AUTH_URL}?"
        f"response_type=code&client_id={SPOTIFY_CLIENT_ID}"
        f"&redirect_uri={SPOTIFY_REDIRECT_URI}"
        f"&scope={SCOPE}"
    )
    return {"auth_url": auth_url}


@app.get("/callback")
def callback(code: str):
    """
    Intercambia el código de autorización por un token de acceso.
    """
    # Configuración de la solicitud para obtener el token
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }

    # Solicitud POST para obtener el token
    response = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
    if response.status_code == 200:
        token_data = response.json()
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data["expires_in"],
        }
    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Error al obtener el token: {response.json()}",
        )


@app.get("/spotify/top-artists")
def get_top_artists(
    access_token: str, limit: int = 10, time_range: str = "medium_term"
):
    """
    Obtiene los artistas más escuchados del usuario autenticado.
    """
    # Encabezados de autorización
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit, "time_range": time_range}

    # Solicitud GET al endpoint de Spotify
    response = requests.get(SPOTIFY_API_URL, headers=headers, params=params)
    if response.status_code == 200:
        artists_data = response.json()
        artists = [
            {
                "name": artist["name"],
                "genres": artist["genres"],
            }
            for artist in artists_data["items"]
        ]
        return {"top_artists": artists}
    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Error al obtener los artistas: {response.json()}",
        )



if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info", reload=True)
