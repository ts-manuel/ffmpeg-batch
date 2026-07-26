import sys
import json
from pathlib import Path
from platformdirs import user_data_dir
from importlib.resources import files
from ffbatch.myconsole import MyConsole


# Global variables
G_APPNAME: str = 'ffbatch'
G_AUTHOR: str = 'tsmanuel'
G_PRESET_DEFAULT_PRESET_FILE = 'presets.json'


class Preset:
    '''
    Load the available presets from a file. The default presets.json is bundled with the package.
    At startup the class checks a folder in the user directory for a presets.json file,
    if it is not found the default one is copied to that location.

    After that the content of the preset is loaded in memory.
    '''


    name : str
    out_file_ext : str
    ffmpeg_args : dict


    def __init__(self, console : MyConsole, name: str):
        self._console = console

        # Check if the presets.json file exists in the user directory,
        # if not copy the default one
        if (not self.get_user_presets_file_path().exists()):
            self._copy_default_presets_to_user_folder()

        # Load required preset
        with self.get_user_presets_file_path().open('r') as f:
            data = json.load(f)

            # Check if the preset argument is specified and is a valid name
            if name == None or not name in data:
                raise ValueError('No valid preset specified')

            # Set member variables
            self.name = name
            self.out_file_ext = self._try_parse_keyword(data[name], 'output_file_ext')
            self.ffmpeg_args = self._try_parse_keyword(data[name], 'ffmpeg_args')


    @staticmethod
    def get_available_preset_names() -> str:
        with Preset.get_user_presets_file_path().open('r') as f:
            presets = json.load(f)
            return [str(x) for x in presets.keys() ]

    @staticmethod
    def get_user_presets_file_path() -> Path:
        """Compute path to the .json config file in the user data directory.

        Returns:
            Path: Path to the .json config file
        """
        return Path(user_data_dir(G_APPNAME, G_AUTHOR)).joinpath(G_PRESET_DEFAULT_PRESET_FILE)


    def _copy_default_presets_to_user_folder(self) -> None:
        """Copy the preset.json file from the default location to the user folder
        """
        config_file_path = self.get_user_presets_file_path()
        config_file_path.parent.mkdir(parents=True, exist_ok=True)

        with files('ffbatch').joinpath(G_PRESET_DEFAULT_PRESET_FILE).open('r') as source, \
            config_file_path.open(mode='w', encoding='utf-8') as destination:
            data = json.load(source)
            json.dump(data, destination, indent=4)


    def _try_parse_keyword(self, data, key : str):
        if not key in data:
            self._console.error(f'wrong syntax in preset file: {'presets.json'}, keyword "{key}" not set for preset "{self.name}"')
        return data[key]


    def __repr__(self):
        return (f'[{self.name}]\n' +
                f'  out_file_ext : {self.out_file_ext}\n' +
                f'  ffmpeg_args .: {self.ffmpeg_args}')