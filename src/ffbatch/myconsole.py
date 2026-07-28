import sys
from rich.console import Console

class MyConsole(Console):
    '''
    Extend the functionality of the Rich Console by adding custom print methods
    for verbose and error output.
    
    Verbose prints only if the verbose_enabled flag if set.
    
    Error prints the message and terminates the application.
    '''

    verbose_enabled : bool = False
    verbose_style : str = 'turquoise2'

    def __init__(self):
        Console.__init__(self)

    def verbose(self, s : str) -> None:
        if self.verbose_enabled:
            self.print(s, style=self.verbose_style, markup=False)

    def error(self, s : str) -> None:
        self.print(f'\n[bold red]error[/bold red]: ', end='')
        self.print(s, markup=False)
        sys.exit(1)