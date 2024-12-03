import requests
import spotipy
import json
import os

from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException

load_dotenv()
app = FastAPI()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

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


@app.get("/user/{id}")
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
        if user is None:
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


@app.put("/user/{id}")
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


@app.delete("/user/{id}")
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


@app.get("/spotify_info")
def get_spotify_info():
    """
    Obtiene información de Spotify del usuario actual.

    Devuelve un diccionario con los artistas y canciones más escuchados del usuario actual.

    Raises:
        HTTPException: Si ocurre un error al obtener los datos de Spotify.
    """
    
    try:
        # Configuración de credenciales de Spotify
        client_credentials_manager = SpotifyClientCredentials(
            SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
        )
        sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

        # Obtener información del usuario actual
        current_user = sp.current_user()

        # Obtener las canciones más escuchadas del usuario
        top_tracks = sp.current_user_top_tracks(limit=10, time_range="medium_term")

        # Preparar la información de las canciones
        tracks_info = []
        for track in top_tracks["items"]:
            tracks_info.append(
                {
                    "track_name": track["name"],
                    "artist": track["artists"][0]["name"],
                }
            )

        # Obtener los artistas más escuchados
        top_artists = sp.current_user_top_artists(limit=10, time_range="medium_term")

        # Preparar la información de los artistas
        artists_info = []
        for artist in top_artists["items"]:
            artists_info.append({"artist_name": artist["name"]})

        # Construir la respuesta
        response = {
            "user": {
                "display_name": current_user["display_name"],
                "spotify_url": current_user["external_urls"]["spotify"],
            },
            "top_tracks": tracks_info,
            "top_artists": artists_info,
        }

        return response

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error al obtener datos de Spotify: {e}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info", reload=True)
