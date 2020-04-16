# Check if EnergyPlus env variables exist already. If not use these defaults
if [[ -z "${ENERGYPLUS_VERSION}" ]]; then
  ENERGYPLUS_VERSION=9.2.0
fi
if [[ -z "${ENERGYPLUS_SHA}" ]]; then
  ENERGYPLUS_SHA=921312fa1d
fi
if [[ -z "${ENERGYPLUS_INSTALL_VERSION}" ]]; then
  ENERGYPLUS_INSTALL_VERSION=9-2-0
fi
if [[ "$TRAVIS_OS_NAME" == "osx" ]]; then
  EXT=dmg
  PLATFORM=Darwin
fi
if [[ "$TRAVIS_OS_NAME" == "linux" ]]; then
  EXT="sh"
  PLATFORM=Linux
fi
if [[ "$TRAVIS_OS_NAME" == "windows" ]]; then
  EXT=exe
  PLATFORM=Windows
fi
# Download EnergyPlus executable
ENERGYPLUS_DOWNLOAD_BASE_URL=https://github.com/NREL/EnergyPlus/releases/download/v$ENERGYPLUS_VERSION
ENERGYPLUS_DOWNLOAD_FILENAME=EnergyPlus-$ENERGYPLUS_VERSION-$ENERGYPLUS_SHA-$PLATFORM-x86_64
ENERGYPLUS_DOWNLOAD_URL=$ENERGYPLUS_DOWNLOAD_BASE_URL/$ENERGYPLUS_DOWNLOAD_FILENAME.$EXT
echo "$ENERGYPLUS_DOWNLOAD_URL"
curl -SL -C - "$ENERGYPLUS_DOWNLOAD_URL" -o "$ENERGYPLUS_DOWNLOAD_FILENAME".$EXT

# Extra downloads
if [[ "$TRAVIS_OS_NAME" == "linux" ]]; then
  ATTCHBASE=97
  ATTCHNUM=8230
fi
if [[ "$TRAVIS_OS_NAME" == "osx" ]]; then
  ATTCHBASE=98
  ATTCHNUM=8232
fi
if [[ "$TRAVIS_OS_NAME" == "windows" ]]; then
  ATTCHBASE=86
  ATTCHNUM=8231
fi
EXTRAS_DOWNLOAD_URL=http://energyplus.helpserve.com/Knowledgebase/Article/GetAttachment/$ATTCHBASE/$ATTCHNUM
curl -SL -C - $EXTRAS_DOWNLOAD_URL -o $ATTCHNUM.zip

# Install EnergyPlus and Extra Downloads
if [ "$TRAVIS_OS_NAME" == "linux" ]; then
  sudo chmod +x "$ENERGYPLUS_DOWNLOAD_FILENAME".$EXT
  printf "y\r" | sudo ./"$ENERGYPLUS_DOWNLOAD_FILENAME".$EXT
  sudo tar zxvf $ATTCHNUM.zip -C /usr/local/EnergyPlus-"$ENERGYPLUS_INSTALL_VERSION"/PreProcess/IDFVersionUpdater
  sudo chmod -R a+rwx /usr/local/EnergyPlus-"$ENERGYPLUS_INSTALL_VERSION"/PreProcess/IDFVersionUpdater
  sudo chmod -R a+rwx /usr/local/EnergyPlus-"$ENERGYPLUS_INSTALL_VERSION"/ExampleFiles
  # cleanup
  sudo rm "$ENERGYPLUS_DOWNLOAD_FILENAME".$EXT
  sudo rm $ATTCHNUM.zip
fi
if [ "$TRAVIS_OS_NAME" == "osx" ]; then
  curl -SLO https://raw.githubusercontent.com/NREL/EnergyPlus/3cf5e1c8e6944e8a7760b80078c6945073cc8364/cmake/qtifw/install_script.qs
  sudo hdiutil attach "$ENERGYPLUS_DOWNLOAD_FILENAME".$EXT
  sudo /Volumes/"$ENERGYPLUS_DOWNLOAD_FILENAME"/"$ENERGYPLUS_DOWNLOAD_FILENAME".app/Contents/MacOS/"$ENERGYPLUS_DOWNLOAD_FILENAME" --verbose --script install_script.qs
  sudo tar zxvf $ATTCHNUM.zip -C /Applications/EnergyPlus-"$ENERGYPLUS_INSTALL_VERSION"/PreProcess
  sudo chmod -R a+rwx /Applications/EnergyPlus-"$ENERGYPLUS_INSTALL_VERSION"/PreProcess/IDFVersionUpdater
  sudo chmod -R a+rwx /Applications/EnergyPlus-"$ENERGYPLUS_INSTALL_VERSION"/ExampleFiles
  # cleanup
  sudo rm install_script.qs
  sudo rm "$ENERGYPLUS_DOWNLOAD_FILENAME".$EXT
  sudo rm $ATTCHNUM.zip
fi
if [ "$TRAVIS_OS_NAME" == "windows" ]; then
  curl -SL -C - https://raw.githubusercontent.com/NREL/EnergyPlus/3cf5e1c8e6944e8a7760b80078c6945073cc8364/cmake/qtifw/install_script.qs -o install_script.qs
  ./$ENERGYPLUS_DOWNLOAD_FILENAME.$EXT --verbose --script install_script.qs
  DEST=C:\\EnergyPlusV"$ENERGYPLUS_INSTALL_VERSION"\\PreProcess\\IDFVersionUpdater
  echo "Extracting and Copying files to... $DEST"
  powershell Expand-Archive -Path $ATTCHNUM.zip -DestinationPath "$DEST" -Force
  # cleanup
  rm -v install_script.qs
  rm -v $ENERGYPLUS_DOWNLOAD_FILENAME.$EXT
  rm -v $ATTCHNUM.zip
fi
