########################################################################
# archetypal Dockerfile
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
#
# Build an image from the dockerfile:
# >>> docker build -t samuelduchese/archetypal .
#
# Push the built image to hub so others can pull/run it:
# >>> docker tag samuelduchesne/archetypal samuelduchesne/archetypal:latest
# >>> docker login
# >>> docker push samuelduchesne/archetypal
#
# Run bash in this container and export final conda environment to a yml file:
# >>> docker run --rm -it -u 0 --name archetypal -v %cd%:/home/jovyan/work samuelduchesne/archetypal /bin/bash
# >>> conda env export -n base > /home/jovyan/work/environment.yml
#
# Run jupyter lab in this container:
# >>> docker run --rm -it --name archetypal -p 8888:8888 -v %cd%:/home/jovyan/work samuelduchesne/archetypal
#
# Stop/delete all local docker containers/images:
# >>> docker stop $(docker ps -aq)
# >>> docker rm $(docker ps -aq)
# >>> docker rmi $(docker images -q)
########################################################################

FROM jupyter/base-notebook
LABEL maintainer="Samuel Letellier-Duchesne <samuel.letellier-duchesne@polymtl.ca>"

# symlink and permissions
USER root
RUN ln -s /opt/conda/bin/jupyter /usr/local/bin
USER $NB_UID

# configure conda and install packages in one RUN to keep image tidy
RUN conda config --set show_channel_urls true && \
    conda config --prepend channels conda-forge && \
    conda update --override-channels -c conda-forge --yes -n base conda && \
    conda update --override-channels -c conda-forge --yes --all && \
    conda install --override-channels -c conda-forge --yes archetypal python-igraph && \
    conda clean --yes --all && \
    conda info --all && \
    conda list

# launch notebook in the local working directory that we mount
WORKDIR /home/samueld/wip

# set default command to launch when container is run
CMD ["jupyter", "lab", "--no-browser", "--NotebookApp.token=''", "--NotebookApp.password=''"]
