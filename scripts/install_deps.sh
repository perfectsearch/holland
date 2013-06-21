#!/bin/bash

python=${PYTHON:-python}
requires=$(cat requirements.txt)

$pip install ${requires}
$python setup.py develop
for path in $(ls -d ${PWD}/plugins/*/)
do
    cd ${path}
    $python setup.py develop
    cd -
done  
