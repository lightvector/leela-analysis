## Leela Analysis Script

This script is a modified version of scripts originally from:
https://bitbucket.org/mkmatlock/sgftools

Currently, it's designed to work with Leela 0.10.0, no guarantees about compatibility with any past or future versions.

Added features and modifications from the original scripts:

   * Leela directly finds your game mistakes on its own and gives you alternate variations.
   * Supports SGFs with handicap and komi. (NOTE: Leela only uses Chinese rules, so if your game was really in Japanese rules,
     in very close endgames or with certain kinds of sekis the analysis may not be correct).
   * A variety of minor tweaks to the script interface and the information output to the SGF.

Note that it is not uncommon for Leela to mess up on tactical situations and give poor suggestions, particularly when it hasn't
realized the life or death of a group yet that is actually already alive or dead. Like all MC bots, it also has a somewhat different
notion than humans of how to wrap up a won game and what moves (despite still being winning) are "mistakes". Take the analysis with
a grain of salt.

### How to Use
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
