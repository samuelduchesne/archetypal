For MacOS/Linux users
=====================

MacOS or Linux users must install Wine_ before running archetypal. This software
will allow MacOS/Linux users to run Windows application (e.g. `trnsidf.exe`).

Wine installation
-----------------

1. In the Terminal, you have to install Homebrew with the following command line:

.. code-block::

    ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

You will have to confirm this action by pressing enter. The Terminal might ask your password,
then you have to enter the Admin password (followed by :guilabel:`&Enter: ⏎`). The installation of Homebrew
should take few seconds or minutes.

2. After installing Homebrew, you have to run 'brew doctor' (the Terminal might ask you)
with the following command line:

.. code-block::

    brew doctor

This action will make Homebrew inspected your system to make sure the installation is correctly set up

3. Then you will need to install Xquartz using Homebrew by typing the following command line:

.. code-block::

    brew cask install xquartz

4. Finally you can install Wine by copying the following command line:

.. code-block::

    brew install wine



.. _Wine: https://www.winehq.org/