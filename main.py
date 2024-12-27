from typing import Optional, Union
import requests
import json
import os
import webbrowser
import time

from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException

load_dotenv()
app = FastAPI()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback"
)
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1/me/top/artists"
SCOPE = "user-top-read"

spotify_tokens = {}

USER_DB = "Tareas/API-Rest/users.json"


def check_file_integrity():
    """
    Verifica la integridad del archivo de usuarios.

    Si el archivo de usuarios no existe, lo crea vacío.

    Returns:
        None
    """
    if not os.path.exists(USER_DB):
        with open(USER_DB, "w") as f:
            json.dump([], f, indent=4)


class User(BaseModel):
    name: str
    email: str
    preferences: list[Union[str, dict]] = []


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
    check_file_integrity()

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
        json.dump(users, f, indent=4)

    return {"message": "El usuario se ha creado correctamente", "Usuario": user_dict}


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
    check_file_integrity()

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

    check_file_integrity()

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
        dict: Un diccionario con un mensaje de confirmación y el usuario actualizado.

    Raises:
        HTTPException: Si el usuario no existe en la base de datos.
    """
    check_file_integrity()

    with open(USER_DB, "r") as f:
        users = json.load(f)
        for i, u in enumerate(users):
            if u["id"] == user_id:
                updated_user = user.model_dump(
                    exclude_unset=True
                )  # Solo actualiza los campos proporcionados
                users[i].update(updated_user)
                with open(USER_DB, "w") as f:
                    json.dump(users, f, indent=4)
                return {"message": "Usuario actualizado correctamente", "Usuario": user}
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


@app.put("/user/add_preferences/{user_id}/{track}/{artist}")
def add_preferences(user_id: int, track: str, artist: str):
    """
    Agrega una preferencia musical a un usuario existente.

    Args:
        user_id (int): El id del usuario a agregar la preferencia.
        track (str): El nombre de la canción.
        artist (str): El nombre del artista de la canción.

    Returns:
        dict: Un diccionario con un mensaje de confirmación y el usuario actualizado.

    Raises:
        HTTPException: Si el usuario no existe en la base de datos.
    """
    access_token = get_spotify_token()

    track_info = get_track_info(access_token, track, artist)
    user = get_user(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user["preferences"].append({"track_info": track_info})
    update_user(user_id, User(**user))
    return {
        "message": "Preferencias agregadas correctamente",
        "Usuario actualizado": user,
    }


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
    check_file_integrity()

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
    Genera la URL de autenticación para Spotify.

    Retorna un diccionario con la clave "auth_url" que contiene la URL de autenticación.
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
    Maneja la respuesta de la autenticación de Spotify.

    Este endpoint es llamado por Spotify después de que el usuario concede permiso
    para acceder a su cuenta. El código de autorización se intercambia por un token
    de acceso que se utiliza para hacer solicitudes a la API de Spotify.

    Args:
        code (str): Código de autorización proporcionado por Spotify.

    Returns:
        dict: Un diccionario con los tokens de acceso y refresh y el tiempo de
        expiración del token de acceso.

    Raises:
        HTTPException: Si ocurre un error al obtener el token de acceso.
    """
    global spotify_tokens

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }

    response = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
    if response.status_code == 200:
        token_data = response.json()

        spotify_tokens = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data["expires_in"],
        }

        return spotify_tokens
    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Error al obtener el token: {response.json()}",
        )


@app.get("/spotify/get_token")
def get_spotify_token():
    """
    Obtiene el token de acceso de Spotify.

    Si no se ha autenticado previamente, abre la ventana de autenticación
    en el navegador predeterminado. Luego, espera hasta que se obtenga el token
    de acceso y lo devuelve.

    Si no se obtiene el token de acceso en 120 segundos, se lanza una excepción.

    Returns:
        str: El token de acceso de Spotify.
    """
    global spotify_tokens

    if not spotify_tokens:
        auth_url = spotify_auth().get("auth_url")
        webbrowser.open(auth_url)

        timeout = 120
        start_time = time.time()

        while not spotify_tokens:
            if time.time() - start_time > timeout:
                raise HTTPException(
                    status_code=408,
                    detail="Se agotó el tiempo de espera. No se pudo obtener el tóken de acceso.",
                )
            time.sleep(1)

    access_token = spotify_tokens["access_token"]

    return access_token


@app.get("/spotify/track_info")
def get_track_info(access_token: str, track: str, artist: str):

    url = "https://api.spotify.com/v1/search"

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"q": f"{track} {artist}", "type": "track", "limit": 1}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        search_data = response.json()
        tracks = [
            {
                "track_name": track["name"],
                "artist": track["artists"][0]["name"],
                "album": track["album"]["name"],
                "release_date": track["album"]["release_date"],
                "album_type": track["album"]["album_type"],
            }
            for track in search_data["tracks"]["items"]
        ]
        return tracks
    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Error al obtener las canciones: {response.json()}",
        )


@app.get("/spotify/top-artists")
def get_top_artists(
    access_token: str, limit: int = 10, time_range: str = "medium_term"
):
    """
    Obtiene los artistas más escuchados del usuario autenticado.

    Args:
        access_token (str): El token de acceso del usuario.
        limit (int, optional): El número de artistas a obtener. Defaults to 10.
        time_range (str, optional): El rango de tiempo para obtener los artistas
            más escuchados. Los valores posibles son "short_term", "medium_term"
            o "long_term". Defaults to "medium_term".

    Returns:
        dict: Un diccionario con una lista de artistas y sus géneros.

    Raises:
        HTTPException: Si ocurre un error al obtener los artistas.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit, "time_range": time_range}

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


@app.get("/spotify/top-tracks")
def get_top_tracks(access_token: str, limit: int = 10, time_range: str = "medium_term"):
    """
    Obtiene las canciones más escuchadas del usuario autenticado.

    Args:
        access_token (str): El token de acceso del usuario.
        limit (int, optional): El número de canciones a obtener. Defaults to 10.
        time_range (str, optional): El rango de tiempo para obtener las canciones
            más escuchadas. Los valores posibles son "short_term", "medium_term"
            o "long_term". Defaults to "medium_term".

    Returns:
        dict: Un diccionario con una lista de canciones y sus detalles.

    Raises:
        HTTPException: Si ocurre un error al obtener las canciones.
    """
    url = "https://api.spotify.com/v1/me/top/tracks"

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit, "time_range": time_range}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        tracks_data = response.json()
        tracks = [
            {
                "track_name": track["name"],
                "artist": track["artists"][0]["name"],
                "album": track["album"]["name"],
            }
            for track in tracks_data["items"]
        ]
        return {"top_tracks": tracks}
    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Error al obtener las canciones: {response.json()}",
        )


@app.get("/spotify/user_info")
def get_user_info():
    access_token = get_spotify_token()

    return {
        "Canciones más escuchadas": get_top_tracks(access_token),
        "Artistas más escuchados": get_top_artists(access_token),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info", reload=True)
