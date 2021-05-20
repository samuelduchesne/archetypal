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
    apt-get install -y wget bzip2 ca-certificates curl git libxml2-dev sudo && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b -p /opt/conda && \
    rm ~/miniconda.sh && \
    /opt/conda/bin/conda clean -tipsy && \
    ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc

ENV TINI_VERSION=v0.16.1
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /usr/bin/tini
RUN chmod +x /usr/bin/tini

# Add EnergyPlus
# Install EnergyPlus
ENV TRAVIS_OS_NAME=linux
ENV ENERGYPLUS_VERSION=9.2.0
COPY install_energyplus.sh install_energyplus.sh
RUN /bin/bash install_energyplus.sh

# Add trnsidf
COPY docker/trnsidf /app/trnsidf

# Copy over environement.yml and requirements-dev.txt
COPY environment.yml environment.yml
COPY requirements-dev.txt requirements-dev.txt
# configure conda and install packages in one RUN to keep image tidy
RUN conda update -n base conda && \
    conda config --prepend channels conda-forge && \
    conda env update -n base -f environment.yml --prune