import cli_ui
from rich.console import Console
from data.config import config

console = Console()


class UploadHelper:
    async def dupe_check(self, dupes, meta, tracker_name):
        if not dupes:
            console.print("[green]No dupes found")
            meta['upload'] = True
            return meta, False
        else:
            if not meta['unattended'] or (meta['unattended'] and meta.get('unattended-confirm', False)):
                console.print()
                dupe_text = "\n".join([d['name'] if isinstance(d, dict) else d for d in dupes])
                console.print()
                cli_ui.info_section(cli_ui.bold, f"Check if these are actually dupes from {tracker_name}!")
                cli_ui.info(dupe_text)
                console.print()
                if meta.get('dupe', False) is False:
                    print()
                    upload = cli_ui.ask_yes_no(f"Upload to {tracker_name} anyway?", default=False)
                    meta['we_asked'] = True
                else:
                    upload = True
                    meta['we_asked'] = False
            else:
                if meta.get('dupe', False) is False:
                    console.print(f"[red]Found potential dupes on {tracker_name}. Aborting. If this is not a dupe, or you would like to upload anyways, pass --skip-dupe-check")
                    upload = False
                else:
                    console.print(f"[yellow]Found potential dupes on {tracker_name}. --skip-dupe-check was passed. Uploading anyways")
                    upload = True

            console.print()
            if upload is False:
                return meta, True
            else:
                for each in dupes:
                    each_name = each['name'] if isinstance(each, dict) else each
                    if each_name == meta['name']:
                        meta['name'] = f"{meta['name']} DUPE?"

                return meta, False

    async def get_confirmation(self, meta):
        if meta['debug'] is True:
            console.print("[bold red]DEBUG: True")
        console.print(f"Prep material saved to {meta['base_dir']}/tmp/{meta['uuid']}")
        console.print()
        console.print("[bold yellow]Database Info[/bold yellow]")
        console.print(f"[bold]Title:[/bold] {meta['title']} ({meta['year']})")
        console.print()
        console.print(f"[bold]Overview:[/bold] {meta['overview']}")
        console.print()
        console.print(f"[bold]Category:[/bold] {meta['category']}")
        if int(meta.get('tmdb', 0)) != 0:
            console.print(f"[bold]TMDB:[/bold] https://www.themoviedb.org/{meta['category'].lower()}/{meta['tmdb']}")
        if int(meta.get('imdb_id', '0')) != 0:
            console.print(f"[bold]IMDB:[/bold] https://www.imdb.com/title/tt{meta['imdb_id']}")
        if int(meta.get('tvdb_id', '0')) != 0:
            console.print(f"[bold]TVDB:[/bold] https://www.thetvdb.com/?id={meta['tvdb_id']}&tab=series")
        if int(meta.get('tvmaze_id', '0')) != 0:
            console.print(f"[bold]TVMaze:[/bold] https://www.tvmaze.com/shows/{meta['tvmaze_id']}")
        if int(meta.get('mal_id', 0)) != 0:
            console.print(f"[bold]MAL:[/bold] https://myanimelist.net/anime/{meta['mal_id']}")
        console.print()
        if int(meta.get('freeleech', '0')) != 0:
            console.print(f"[bold]Freeleech:[/bold] {meta['freeleech']}")
        tag = "" if meta['tag'] == "" else f" / {meta['tag'][1:]}"
        res = meta['source'] if meta['is_disc'] == "DVD" else meta['resolution']
        console.print(f"{res} / {meta['type']}{tag}")
        if meta.get('personalrelease', False) is True:
            console.print("[bold green]Personal Release![/bold green]")
        console.print()
        if meta.get('unattended', False) is False:
            await self.get_missing(meta)
            ring_the_bell = "\a" if config['DEFAULT'].get("sfx_on_prompt", True) is True else ""
            if ring_the_bell:
                console.print(ring_the_bell)

            if meta.get('is disc', False) is True:
                meta['keep_folder'] = False

            if meta.get('keep_folder') and meta['isdir']:
                console.print("[bold yellow]Uploading with --keep-folder[/bold yellow]")
                kf_confirm = input("You specified --keep-folder. Uploading in folders might not be allowed. Proceed? [y/N]: ").strip().lower()
                if kf_confirm != 'y':
                    console.print("[bold red]Aborting...[/bold red]")
                    exit()

            console.print("[bold yellow]Is this correct?[/bold yellow]")
            console.print(f"[bold]Name:[/bold] {meta['name']}")
            confirm = input("Correct? [y/N]: ").strip().lower() == 'y'
        else:
            console.print(f"[bold]Name:[/bold] {meta['name']}")
            confirm = True

        return confirm

    async def get_missing(self, meta):
        info_notes = {
            'edition': 'Special Edition/Release',
            'description': "Please include Remux/Encode Notes if possible",
            'service': "WEB Service e.g.(AMZN, NF)",
            'region': "Disc Region",
            'imdb': 'IMDb ID (tt1234567)',
            'distributor': "Disc Distributor e.g.(BFI, Criterion)"
        }
        missing = []
        if meta.get('imdb_id', '0') == '0':
            meta['imdb_id'] = '0'
            meta['potential_missing'].append('imdb_id')
        for each in meta['potential_missing']:
            if str(meta.get(each, '')).strip() in ["", "None", "0"]:
                missing.append(f"--{each} | {info_notes.get(each, '')}")
        if missing:
            cli_ui.info_section(cli_ui.yellow, "Potentially missing information:")
            for each in missing:
                cli_ui.info(each)
        console.print()
