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
# On Linux/MacOs
# >>> docker run --rm -it -p 8888:8888 -v "$PWD":/home/archetypal/wip samuelduchesne/archetypal
# On Windows (With PowerShell, use ${PWD})
# >>> docker run --rm -it -p 8888:8888 -v %cd%:/home/archetypal/wip samuelduchesne/archetypal
#
# Stop/delete all local docker containers/images:
# >>> docker stop $(docker ps -aq)
# >>> docker rm $(docker ps -aq)
# >>> docker rmi $(docker images -q)
########################################################################

FROM scottyhardy/docker-wine:latest

LABEL maintainer="Samuel Letellier-Duchesne <samuel.letellier-duchesne@polymtl.ca>"
LABEL url="https://github.com/samuelduchesne/archetypal"
LABEL description="archetypal: Retrieve, construct, simulate, and analyse building archetypes"

# Get git related dependecies
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV PATH /opt/conda/bin:$PATH

RUN apt-get update --fix-missing && \
    apt-get install -y wget bzip2 ca-certificates curl git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-4.5.11-Linux-x86_64.sh -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b -p /opt/conda && \
    rm ~/miniconda.sh && \
    /opt/conda/bin/conda clean -tipsy && \
    ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc

ENV TINI_VERSION v0.16.1
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /usr/bin/tini
RUN chmod +x /usr/bin/tini

# Add EnergyPlus
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

# Add trnsidf
COPY ./trnsidf /app/trnsidf

# configure conda and install packages in one RUN to keep image tidy
RUN git clone --branch=develop --verbose https://github.com/samuelduchesne/archetypal.git && \
    cd archetypal && \
    conda update -n base conda && \
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
ENTRYPOINT ["/usr/bin/entrypoint"]
# set default command to launch when container is run
CMD ["jupyter", "lab", "--ip='0.0.0.0'", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''", "--NotebookApp.password=''"]

# to test, import archetypal and print its version
RUN ipython -c "import archetypal; print(archetypal.__version__)"