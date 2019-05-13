########################################################################
# archetypal Dockerfile
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
#
# Build an image from the dockerfile:
# >>> cd ./docker
# >>> docker build -t samuelduchese/archetypal .
#
# Push the built image to hub so others can pull/run it:
# >>> docker tag samuelduchesne/archetypal samuelduchesne/archetypal:latest
# >>> docker login
# >>> docker push samuelduchesne/archetypal
#
# Run bash in this container and export final conda environment to a yml file:
# >>> docker run --rm -it -u 0 --name archetypal -v "$PWD":/home/archetypal/wip samuelduchesne/archetypal /bin/bash
# >>> conda env export -n base > /home/archetypal/wip/environment.yml
#
# Run jupyter lab in this container:
# >>> docker run --rm -it -p 8888:8888 -v "$PWD":/home/archetypal/wip samuelduchesne/archetypal
#
# Stop/delete all local docker containers/images:
# >>> docker stop $(docker ps -aq)
# >>> docker rm $(docker ps -aq)
# >>> docker rmi $(docker images -q)
########################################################################

FROM continuumio/miniconda3
LABEL maintainer="Samuel Letellier-Duchesne <samuel.letellier-duchesne@polymtl.ca>"
LABEL url="https://github.com/samuelduchesne/archetypal"
LABEL description="archetypal: Retrieve, construct, simulate, and analyse building archetypes"

# Clone repo
RUN git clone --branch=develop https://github.com/samuelduchesne/archetypal.git

# Before install
ENV ENERGYPLUS_VERSION=8.9.0
ENV ENERGYPLUS_SHA=40101eaafd
ENV ENERGYPLUS_INSTALL_VERSION=8-9-0
ENV PLATFORM=Linux
ENV EXT=sh
ENV ENERGYPLUS_DOWNLOAD_BASE_URL=https://github.com/NREL/EnergyPlus/releases/download/v$ENERGYPLUS_VERSION
ENV ENERGYPLUS_DOWNLOAD_FILENAME=EnergyPlus-$ENERGYPLUS_VERSION-$ENERGYPLUS_SHA-$PLATFORM-x86_64
ENV ENERGYPLUS_DOWNLOAD_URL=$ENERGYPLUS_DOWNLOAD_BASE_URL/$ENERGYPLUS_DOWNLOAD_FILENAME.$EXT
RUN curl -SLO $ENERGYPLUS_DOWNLOAD_URL && \
    chmod +x $ENERGYPLUS_DOWNLOAD_FILENAME.$EXT && \
    echo "y\r" | ./$ENERGYPLUS_DOWNLOAD_FILENAME.$EXT && \
    rm $ENERGYPLUS_DOWNLOAD_FILENAME.$EXT

# configure conda and install packages in one RUN to keep image tidy
WORKDIR archetypal
RUN conda update -n base conda && \
    conda config --append channels conda-forge && \
    conda env update -n archetypal -f environment.yml --prune && \
    conda install -n archetypal --file requirements-dev.txt && \
    conda install --strict-channel-priority --update-all --force-reinstall --yes jupyterlab python-igraph && \
    conda clean --yes --all && \
    conda info --all && \
    conda list && \
    echo "source activate archetypal" > ~/.bashrc && \
    python setup.py install
ENV PATH /opt/conda/envs/archetypal/bin:$PATH

# launch notebook in the local working directory that we mount
WORKDIR /home/archetypal/wip

# set default command to launch when container is run
CMD ["jupyter", "lab", "--ip='0.0.0.0'", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''", "--NotebookApp.password=''"]

# to test, import archetypal and print its version
RUN ipython -c "import archetypal; print(archetypal.__version__)"