==Leela Analysis Script==
This script is a modified version of scripts originally from https://bitbucket.org/mkmatlock/sgftools
Currently, it's designed to work with Leela 0.10.0, no guarantees about compatibility with any past or future versions.

=How to Use=
First, download and install the "engine only"/"commandline"/"GTP" version of Leela 0.10.0 from:
https://sjeng.org/leela.html

Clone this repository to a local directory:

    git clone https://github.com/lightvector/leela_analysis
    cd leela_analysis

Then simply run the script to analyze a game, providing the path to the leela executable, such as Leela0100GTP.exe.

    sgfanalyze.py my_game.sgf --leela /PATH/TO/LEELA.exe > my_game_analyzed.sgf

By default, Leela will go through every position in the provided game and find what it considers to be all the mistakes by both players,
producing an SGF file where it highlights those mistakes and provides alternative variations it would have expected. It will probably take
an hour or two to run.

Run the script with --help to see other options you can configure. You can change the amount of time Leela will analyze for, change how
much effort it puts in to making variations versus just analyzing the main game, or select just a subrange of the game to analyze.
