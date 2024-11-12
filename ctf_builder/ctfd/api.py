import datetime
import os.path
import re
import typing

import requests

from ..error import DeployError, LibError
from .models import (
    CTFdAccessToken,
    CTFdChallenge,
    CTFdFile,
    CTFdFileUpload,
    CTFdFlag,
    CTFdHint,
    CTFdResponse,
    CTFdSetup,
    CTFdTeam,
    CTFdUser,
)
from .session import CTFdSession


NONCE_RE = re.compile(r"<input id=\"nonce\".+?value=\"(.+?)\">")
CSRF_RE = re.compile(r"'csrfNonce': \"(.*?)\"")

T = typing.TypeVar("T")


class CTFdAPI:
    __session: CTFdSession

    def __init__(self, session: CTFdSession):
        self.__session = session

    @property
    def session(self) -> CTFdSession:
        return self.__session

    @classmethod
    def login(
        cls, url: str, name: str, password: str, verify_ssl: bool = True
    ) -> typing.Optional["CTFdAPI"]:
        access_token = cls.create_access_token_auth(url, name, password, verify_ssl)
        if access_token is None:
            return None

        return CTFdAPI(
            CTFdSession(url=url, access_token=access_token, verify_ssl=verify_ssl)
        )

    @classmethod
    def setup(
        cls, url: str, data: CTFdSetup, root: str = "", verify_ssl: bool = True
    ) -> typing.Sequence[LibError]:
        sess = requests.Session()

        if (nonce := cls.read_nonce(sess, f"{url}/setup", verify_ssl)) is None:
            return [DeployError(context="Nonce", msg="failed to get")]

        data.nonce = nonce

        form = data.model_dump(mode="json")
        files = {}

        for key in ["ctf_logo", "ctf_banner", "ctf_small_icon"]:
            if key not in form or not form[key]:
                continue

            files[key] = os.path.join(root, form[key])

        res = sess.post(f"{url}/setup", data=form, files=files, verify=verify_ssl)

        if res.status_code != 200:
            return [DeployError(context="Setup", msg="failed to deploy")]

        return []

    def get_challenge_by_name(
        self, name: str
    ) -> typing.Tuple[
        typing.Optional[typing.List[CTFdChallenge]], typing.Sequence[LibError]
    ]:
        res = self.__session.get("/challenges", data={"name": name})

        return self.__handle(
            res=CTFdResponse[typing.Optional[typing.List[CTFdChallenge]]](**res.json()),
            context=f"Challenge {name}",
            msg="failed to get",
        )

    def create_challenge(
        self, challenge: CTFdChallenge
    ) -> typing.Tuple[typing.Optional[CTFdChallenge], typing.Sequence[LibError]]:
        res = self.__session.post(
            "/challenges", data=self.__cleanup_create(challenge.model_dump(mode="json"))
        )

        return self.__handle(
            res=CTFdResponse[typing.Optional[CTFdChallenge]](**res.json()),
            context=f"Challenge {challenge.name}",
            msg="failed to create",
        )

    def update_challenge(
        self, challenge: CTFdChallenge
    ) -> typing.Tuple[typing.Optional[CTFdChallenge], typing.Sequence[LibError]]:
        res = self.__session.patch(
            f"/challenges/{challenge.id}",
            data=self.__cleanup(challenge.model_dump(mode="json")),
        )

        return self.__handle(
            res=CTFdResponse[typing.Optional[CTFdChallenge]](**res.json()),
            context=f"Challenge {challenge.name}",
            msg="failed to update",
        )

    def delete_challenge(self, challenge_id: int) -> bool:
        res = self.__session.delete(f"/challenges/{challenge_id}")

        return res.json()["success"] is True

    def get_flags_in_challenge(
        self, challenge_id: int
    ) -> typing.Tuple[
        typing.Optional[typing.List[CTFdFlag]], typing.Sequence[LibError]
    ]:
        res = self.__session.get("/flags", data={"challenge_id": challenge_id})

        return self.__handle(
            res=CTFdResponse[typing.Optional[typing.List[CTFdFlag]]](**res.json()),
            context=f"Challenge {challenge_id}",
            msg="failed to get flags",
        )

    def create_flag(
        self, flag: CTFdFlag
    ) -> typing.Tuple[typing.Optional[CTFdFlag], typing.Sequence[LibError]]:
        res = self.__session.post(
            "/flags", data=self.__cleanup_create(flag.model_dump(mode="json"))
        )

        return self.__handle(
            res=CTFdResponse[typing.Optional[CTFdFlag]](**res.json()),
            context=f"Flag {flag.content}",
            msg="failed to create",
        )

    def delete_flag(self, flag_id: int) -> bool:
        res = self.__session.delete(f"/flags/{flag_id}")

        return res.json()["success"] is True

    def get_files_in_challenge(
        self, challenge_id: int
    ) -> typing.Tuple[
        typing.Optional[typing.List[CTFdFile]], typing.Sequence[LibError]
    ]:
        res = self.__session.get(f"/challenges/{challenge_id}/files")

        return self.__handle(
            res=CTFdResponse[typing.Optional[typing.List[CTFdFile]]](**res.json()),
            context=f"Challenge {challenge_id}",
            msg="failed to get files",
        )

    def create_file(
        self, upload: CTFdFileUpload
    ) -> typing.Tuple[
        typing.Optional[typing.List[CTFdFile]], typing.Sequence[LibError]
    ]:
        res = self.__session.post_data(
            "/files",
            data={"challenge": upload.challenge, "type": upload.type.value},
            files={"file": (upload.file_name, upload.file_data)},
        )

        return self.__handle(
            res=CTFdResponse[typing.Optional[typing.List[CTFdFile]]](**res.json()),
            context=f"Challenge {upload.challenge}",
            msg="failed to upload file",
        )

    def delete_file(self, file_id: int) -> bool:
        res = self.__session.delete(f"/files/{file_id}")

        return res.json()["success"] is True

    def get_hints_in_challenge(
        self, challenge_id: int
    ) -> typing.Tuple[
        typing.Optional[typing.List[CTFdHint]], typing.Sequence[LibError]
    ]:
        res = self.__session.get("/hints", data={"challenge_id": challenge_id})

        return self.__handle(
            res=CTFdResponse[typing.Optional[typing.List[CTFdHint]]](**res.json()),
            context=f"Challenge {challenge_id}",
            msg="failed to get hints",
        )

    def create_hint(
        self, hint: CTFdHint
    ) -> typing.Tuple[typing.Optional[CTFdHint], typing.Sequence[LibError]]:
        res = self.__session.post(
            "/hints", data=self.__cleanup_create(hint.model_dump(mode="json"))
        )

        return self.__handle(
            res=CTFdResponse[typing.Optional[CTFdHint]](**res.json()),
            context=f"Hint for Challenge {hint.challenge_id}",
            msg="failed to create",
        )

    def delete_hint(self, hint_id: int) -> bool:
        res = self.__session.delete(f"/hints/{hint_id}")

        return res.json()["success"] is True

    def get_users_by_query(
        self, query: str
    ) -> typing.Tuple[
        typing.Optional[typing.List[CTFdUser]], typing.Sequence[LibError]
    ]:
        res = self.__session.get("/users", data={"q": query})

        return self.__handle(
            res=CTFdResponse[typing.Optional[typing.List[CTFdUser]]](**res.json()),
            context=f"Users {query}",
            msg="failed to get",
        )

    def get_users_in_team(
        self, team_id: int
    ) -> typing.Tuple[typing.Optional[typing.List[int]], typing.Sequence[LibError]]:
        res = self.__session.get(f"/teams/{team_id}/members")

        return self.__handle(
            res=CTFdResponse[typing.Optional[typing.List[int]]](**res.json()),
            context=f"Team {team_id}",
            msg="failed to get users",
        )

    def add_user_to_team(self, team_id: int, user_id: int) -> bool:
        res = self.__session.post(
            f"/teams/{team_id}/members",
            data={"user_id": user_id},
        )

        return res.status_code == 200

    def create_user(
        self, user: CTFdUser
    ) -> typing.Tuple[typing.Optional[CTFdUser], typing.Sequence[LibError]]:
        res = self.__session.post(
            "/users", data=self.__cleanup_create(user.model_dump(mode="json"))
        )

        return self.__handle(
            res=CTFdResponse[typing.Optional[CTFdUser]](**res.json()),
            context=f"User {user.email}",
            msg="failed to create",
        )

    def update_user(
        self, user: CTFdUser
    ) -> typing.Tuple[typing.Optional[CTFdUser], typing.Sequence[LibError]]:
        res = self.__session.patch(
            f"/users/{user.id}", data=self.__cleanup(user.model_dump(mode="json"))
        )

        return self.__handle(
            res=CTFdResponse[typing.Optional[CTFdUser]](**res.json()),
            context=f"User {user.email}",
            msg="failed to update",
        )

    def get_teams_by_query(
        self, query: str
    ) -> typing.Tuple[
        typing.Optional[typing.List[CTFdTeam]], typing.Sequence[LibError]
    ]:
        res = self.__session.get("/teams", data={"q": query})

        return self.__handle(
            res=CTFdResponse[typing.Optional[typing.List[CTFdTeam]]](**res.json()),
            context=f"Teams {query}",
            msg="failed to get",
        )

    def create_team(
        self, team: CTFdTeam
    ) -> typing.Tuple[typing.Optional[CTFdTeam], typing.Sequence[LibError]]:
        res = self.__session.post(
            "/teams", data=self.__cleanup_create(team.model_dump(mode="json"))
        )

        return self.__handle(
            res=CTFdResponse[typing.Optional[CTFdTeam]](**res.json()),
            context=f"Team {team.email}",
            msg="failed to create",
        )

    def update_team(
        self, team: CTFdTeam
    ) -> typing.Tuple[typing.Optional[CTFdTeam], typing.Sequence[LibError]]:
        res = self.__session.patch(
            f"/teams/{team.id}", self.__cleanup(team.model_dump(mode="json"))
        )

        return self.__handle(
            res=CTFdResponse[typing.Optional[CTFdTeam]](**res.json()),
            context=f"Team {team.email}",
            msg="failed to update",
        )

    @classmethod
    def read_nonce(
        cls, sess: requests.Session, url: str, verify_ssl: bool = True
    ) -> typing.Optional[str]:
        res = sess.get(url, verify=verify_ssl)

        match = NONCE_RE.findall(res.text)

        return match[0] if match else None

    @classmethod
    def read_csrf(
        cls, sess: requests.Session, url: str, verify_ssl: bool = True
    ) -> typing.Optional[str]:
        res = sess.get(url, verify=verify_ssl)

        match = CSRF_RE.findall(res.text)

        return match[0] if match else None

    @classmethod
    def create_access_token_auth(
        cls, url: str, name: str, password: str, verify_ssl: bool = True
    ) -> typing.Optional[CTFdAccessToken]:
        sess = requests.Session()

        nonce = cls.read_nonce(sess, f"{url}/login", verify_ssl)

        res = sess.post(
            f"{url}/login",
            data={"name": name, "password": password, "nonce": nonce},
            verify=verify_ssl,
        )
        if res.status_code != 200:
            return None

        csrf = cls.read_csrf(sess, f"{url}/settings", verify_ssl)

        expiration = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            days=1
        )

        res = sess.post(
            f"{url}/api/v1/tokens",
            headers={"CSRF-Token": csrf},
            json={
                "description": "Created via ctf-builder",
                "expiration": expiration.date().isoformat(),
            },
            verify=verify_ssl,
        )

        data = CTFdResponse[CTFdAccessToken](**res.json())
        if not data.success:
            return None

        return data.data

    @classmethod
    def __handle(
        cls, res: CTFdResponse[T], context: str = "", msg: str = ""
    ) -> typing.Tuple[typing.Optional[T], typing.Sequence[LibError]]:
        if res.success:
            return res.data, []

        return None, [
            DeployError(
                context=context, msg=msg, error=ValueError(res.message or res.errors)
            )
        ]

    @classmethod
    def __cleanup(
        cls, data: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
        out = {}

        for k, v in data.items():
            if v is None:
                continue

            out[k] = v

        return out

    @classmethod
    def __cleanup_create(
        cls, data: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
        out = cls.__cleanup(data)

        del out["id"]

        return out
