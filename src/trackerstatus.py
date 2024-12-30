import asyncio
import os
from torf import Torrent
from src.trackers.PTP import PTP
from src.trackersetup import TRACKER_SETUP, tracker_class_map
from src.console import console
from data.config import config
from src.trackers.COMMON import COMMON
from src.clients import Clients
from src.uphelper import UploadHelper
from src.imdb import get_imdb_info_api
from src.torrentcreate import create_base_from_existing_torrent
import cli_ui
import copy


async def process_all_trackers(meta):
    tracker_status = {}
    successful_trackers = 0
    common = COMMON(config=config)
    client = Clients(config=config)
    tracker_setup = TRACKER_SETUP(config=config)
    helper = UploadHelper()
    meta_lock = asyncio.Lock()  # noqa F841

    async def process_single_tracker(tracker_name, shared_meta):
        nonlocal successful_trackers
        local_meta = copy.deepcopy(shared_meta)  # Ensure each task gets its own copy of meta
        local_tracker_status = {'banned': False, 'skipped': False, 'dupe': False, 'upload': False}
        disctype = local_meta.get('disctype', None)
        tracker_name = tracker_name.replace(" ", "").upper().strip()

        if local_meta['name'].endswith('DUPE?'):
            local_meta['name'] = local_meta['name'].replace(' DUPE?', '')

        if tracker_name in tracker_class_map:
            tracker_class = tracker_class_map[tracker_name](config=config)
            if tracker_name in {"THR", "PTP"}:
                if local_meta.get('imdb_id', '0') == '0':
                    imdb_id = "0" if local_meta['unattended'] else cli_ui.ask_string("Unable to find IMDB id, please enter e.g.(tt1234567)")
                    if imdb_id == "":
                        meta['imdb_id'] = "0"
                    else:
                        meta['imdb_id'] = imdb_id.replace('tt', '').zfill(7)

            if tracker_name == "PTP":
                console.print("[yellow]Searching for Group ID on PTP")
                ptp = PTP(config=config)
                groupID = await ptp.get_group_by_imdb(local_meta['imdb_id'])
                if groupID is None:
                    console.print("[yellow]No Existing Group found")
                    if local_meta.get('youtube', None) is None or "youtube" not in str(local_meta.get('youtube', '')):
                        youtube = "" if local_meta['unattended'] else cli_ui.ask_string("Unable to find youtube trailer, please link one e.g.(https://www.youtube.com/watch?v=dQw4w9WgXcQ)", default="")
                        meta['youtube'] = youtube
                meta['ptp_groupID'] = groupID

            if tracker_setup.check_banned_group(tracker_class.tracker, tracker_class.banned_groups, local_meta):
                console.print(f"[red]Tracker '{tracker_name}' is banned. Skipping.[/red]")
                local_tracker_status['banned'] = True

            if tracker_name not in {"THR", "PTP", "TL"}:
                dupes = await tracker_class.search_existing(local_meta, disctype)
            elif tracker_name == "PTP":
                dupes = await ptp.search_existing(groupID, local_meta, disctype)

            if 'skipping' not in local_meta or local_meta['skipping'] is None:
                dupes = await common.filter_dupes(dupes, local_meta, tracker_name)
                local_meta, is_dupe = await helper.dupe_check(dupes, local_meta, tracker_name)
                if is_dupe:
                    console.print(f"[red]Skipping upload on {tracker_name}[/red]")
                    local_tracker_status['dupe'] = True
            elif local_meta['skipping']:
                local_tracker_status['skipped'] = True

            if tracker_name == "MTV":
                if not local_tracker_status['banned'] and not local_tracker_status['skipped'] and not local_tracker_status['dupe']:
                    tracker_config = config['TRACKERS'].get(tracker_name, {})
                    if str(tracker_config.get('prefer_mtv_torrent', 'false')).lower() == "true":
                        local_meta['prefer_small_pieces'] = True
                    else:
                        local_meta['prefer_small_pieces'] = False
                    if str(tracker_config.get('skip_if_rehash', 'false')).lower() == "true":
                        torrent_path = os.path.abspath(f"{local_meta['base_dir']}/tmp/{local_meta['uuid']}/BASE.torrent")
                        if not os.path.exists(torrent_path):
                            check_torrent = await client.find_existing_torrent(local_meta)
                            if check_torrent:
                                console.print(f"[yellow]Existing torrent found on {check_torrent}[yellow]")
                                await create_base_from_existing_torrent(check_torrent, local_meta['base_dir'], local_meta['uuid'])
                                torrent = Torrent.read(torrent_path)
                                if torrent.piece_size > 8388608:
                                    console.print("[yellow]No existing torrent found with piece size lesser than 8MB[yellow]")
                                    local_tracker_status['skipped'] = True
                        elif os.path.exists(torrent_path):
                            torrent = Torrent.read(torrent_path)
                            if torrent.piece_size > 8388608:
                                console.print("[yellow]Existing torrent found with piece size greater than 8MB[yellow]")
                                local_tracker_status['skipped'] = True

            if local_meta.get('skipping') is None and not local_tracker_status['dupe'] and tracker_name == "PTP":
                if local_meta.get('imdb_info', {}) == {}:
                    meta['imdb_info'] = await get_imdb_info_api(local_meta['imdb_id'], local_meta)

            we_already_asked = local_meta.get('we_asked', False)

            if not local_meta['debug']:
                if not local_tracker_status['banned'] and not local_tracker_status['skipped'] and not local_tracker_status['dupe']:
                    console.print(f"[bold yellow]Tracker '{tracker_name}' passed all checks.")
                    if (
                        not local_meta['unattended']
                        or (local_meta['unattended'] and local_meta.get('unattended-confirm', False))
                    ) and not we_already_asked:
                        edit_choice = "y" if local_meta['unattended'] else input("Enter 'y' to upload, or press enter to skip uploading:")
                        if edit_choice.lower() == 'y':
                            local_tracker_status['upload'] = True
                            successful_trackers += 1
                        else:
                            local_tracker_status['upload'] = False
                    else:
                        local_tracker_status['upload'] = True
                        successful_trackers += 1
            else:
                local_tracker_status['upload'] = True
                successful_trackers += 1
            meta['we_asked'] = False

        return tracker_name, local_tracker_status

    if meta.get('unattended', False):
        tasks = [process_single_tracker(tracker_name, meta) for tracker_name in meta['trackers']]
        results = await asyncio.gather(*tasks)
        for tracker_name, status in results:
            tracker_status[tracker_name] = status
    else:
        for tracker_name in meta['trackers']:
            tracker_name, status = await process_single_tracker(tracker_name, meta)
            tracker_status[tracker_name] = status

    if meta['debug']:
        console.print("\n[bold]Tracker Processing Summary:[/bold]")
        for t_name, status in tracker_status.items():
            banned_status = 'Yes' if status['banned'] else 'No'
            skipped_status = 'Yes' if status['skipped'] else 'No'
            dupe_status = 'Yes' if status['dupe'] else 'No'
            upload_status = 'Yes' if status['upload'] else 'No'
            console.print(f"Tracker: {t_name} | Banned: {banned_status} | Skipped: {skipped_status} | Dupe: {dupe_status} | [yellow]Upload:[/yellow] {upload_status}")
        console.print(f"\n[bold]Trackers Passed all Checks:[/bold] {successful_trackers}")

    meta['tracker_status'] = tracker_status
    return successful_trackers
