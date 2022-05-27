import logging
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render
from esi.decorators import token_required
from eveuniverse.models import EveEntity

from datetime import datetime, timedelta
import json
import requests

logger = logging.getLogger(__name__)

_scopes = [
    'esi-industry.read_character_jobs.v1',
    'esi-industry.read_corporation_jobs.v1',
    'esi-universe.read_structures.v1',
]

cache_facility_id = {}
cache_character_id = {}


@login_required
@permission_required("industry.view_industry")
@token_required(scopes=_scopes)
def index(request, t):
# def index(request):
    # char_name = request.user.profile.main_character.character_name
    user_id = request.user.profile.main_character.character_id
    corp_id = request.user.profile.main_character.corporation_id

    # from esi.models import Token, Scope
    # scope = Scope.objects.filter(name__in=_scopes)
    # t = Token.objects.filter(user=request.user.pk, scopes=scope.id).first()

    # tokens = Token.objects.filter(user__pk=request.user.pk).require_scopes(_scopes).require_valid()
    # if not tokens.exists():
    #     tokens = []

    _request_headers = {
        'accept': 'application/json',
        'Cache-Control': 'no-cache',
        'authorization': 'Bearer ' + t.valid_access_token()
    }

    to_screen = {}
    xxx = list()
    jobs = list()

    jobs = _get_personal_jobs(user_id, _request_headers)
    xxx = _process_jobs(_request_headers, jobs)

    jobs = _get_corp_jobs(corp_id, _request_headers)
    _corp_jobs = _process_jobs(_request_headers, jobs, True)

    if _corp_jobs:
        xxx += _corp_jobs

    context = {
        "items": xxx,
        "character_name": t.character_name
        # "tokens": tokens
        # "items": paginator.get_page(page_number),
    }

    # TODO salvar no banco
    cache_facility_id = {}
    cache_character_id = {}

    return render(request, "industry/index.html", context)


def _process_jobs(_request_headers, jobs, is_corp: bool = False) -> list:
    _processed = list()

    if jobs:
        for j in jobs:
            to_screen = dict()
            to_screen['is_corp_job'] = is_corp

            a = EveEntity.objects.get_or_create_esi(id=j.get('blueprint_type_id'))[0]
            to_screen['blueprint_name'] = a.name
            to_screen['blueprint_id'] = a.id

            to_screen['activity_id'] = _get_activity_by_id(j.get('activity_id'))

            to_screen['duration'] = _secondsToTime(j.get('duration'))
            to_screen['start_date'] = _fromStrToDate(j.get('start_date'))
            to_screen['end_date'] = _fromStrToDate(j.get('end_date'))
            to_screen['status'] = j.get('status')

            station = _get_structure(_request_headers, j.get('facility_id'))
            to_screen['station_name'] = station
            to_screen['installer_id'] = j.get('installer_id')

            if is_corp:
                to_screen['installer_name'] = _get_character_name(_request_headers, to_screen['installer_id'])

            _processed.append(to_screen)

        # {'activity_id': 3,
        #  'blueprint_id': 1038474861093,
        #  'blueprint_location_id': 1031301666925,
        #  'blueprint_type_id': 31363,
        #  'cost': 15893293.0,
        #  'duration': 1206170,
        #  'end_date': '2022-05-18T01:32:50Z',
        #  'facility_id': 1031301666925,
        #  'installer_id': 853816661,
        #  'job_id': 489411241,
        #  'licensed_runs': 30,
        #  'output_location_id': 1031301666925,
        #  'probability': 1.0,
        #  'product_type_id': 31363,
        #  'runs': 4,
        #  'start_date': '2022-05-04T02:30:00Z',
        #  'station_id': 1031301666925,
        #  'status': 'active'}

        # orders = OrderSheet.objects.filter(user=request.user).order_by('created_at').order_by('completed')
        # paginator = Paginator(orders, 5)
        # page_number = request.GET.get('page', 1)

    return _processed


def _get_activity_by_id(activity_id: int) -> str:
    activities = {
        1: "Manufacturing",
        2: "Researching Technology",
        3: "Time Efficiency Research",
        4: "Material Efficiency Research",
        5: "Copying",
        6: "Duplicating",
        7: "Reverse Engineering",
        8: "Invention",
    }

    return activities[activity_id]


def _get_structure(_request_headers, facility_id):
    try:
        if facility_id in cache_facility_id.keys():
            return cache_facility_id.get(facility_id)

        # get structure
        r = requests.get(
            f'https://esi.evetech.net/latest/universe/structures/{facility_id}/?datasource=tranquility',
            headers=_request_headers
        )
        if r.status_code == 200:
            station = json.loads(r.content)
            cache_facility_id[facility_id] = station['name']
            return station['name']
            # {'name': 'F69O-M - Mr DATA',
            #  'owner_id': 944838017,
            #  'position': {'x': -627816800940.0, 'y': -24279672349.0, 'z': -838289040685.0},
            #  'solar_system_id': 30002381,
            #  'type_id': 35825}
    except:
        return None


def _get_character_name(_request_headers, character_id):
    try:
        if character_id in cache_character_id.keys():
            return cache_character_id.get(character_id)

        # get character name
        r = requests.get(
            f'https://esi.evetech.net/latest/characters/{character_id}/?datasource=tranquility',
            headers=_request_headers
        )
        if r.status_code == 200:
            character = json.loads(r.content)
            cache_character_id[character_id] = character['name']
            return character['name']
        # { "alliance_id": 673381830,
        #     "birthday": "2020-08-05T19:18:19Z",
        #     "bloodline_id": 5,
        #     "corporation_id": 98680170,
        #     "description": "",
        #     "gender": "male",
        #     "name": "Dharius Redwing",
        #     "race_id": 4,
        #     "security_status": 5.010539505 }
    except:
        return None


def _get_personal_jobs(user_id: int, _request_headers: dict, completed: bool = False):
    try:
        _url = f'https://esi.evetech.net/latest/characters/{user_id}/industry/jobs/?datasource=tranquility'

        if completed:
            _url = _url + '&include_completed=true'

        r = requests.get(
            _url,
            headers=_request_headers
        )

        if r.status_code == 200:
            return json.loads(r.content)
    except requests.exceptions.ConnectionError:
        logger.error("connection failed")
        return None
    else:
        logger.error(f'requests error {r.status_code}')
        return None


def _get_corp_jobs(corp_id: int, _request_headers: dict, completed: bool = False):
    try:
        _url = f'https://esi.evetech.net/latest/corporations/{corp_id}/industry/jobs/?datasource=tranquility'

        if completed:
            _url = _url + '&include_completed=true'

        r = requests.get(
            _url,
            headers=_request_headers
        )

        if r.status_code == 200:
            return json.loads(r.content)
    except requests.exceptions.ConnectionError:
        logger.error("connection failed")
        return None
    else:
        logger.error(f'requests error {r.status_code}')
        return None


def _secondsToTime(seconds: int) -> str:
    return str(timedelta(seconds=seconds))


def _fromStrToDate(date_time_str: str) -> datetime:
    time_obj = datetime.strptime(date_time_str, '%Y-%m-%dT%H:%M:%SZ')
    return time_obj
