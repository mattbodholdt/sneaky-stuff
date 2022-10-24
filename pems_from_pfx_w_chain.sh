#!/usr/bin/env bash

## take pfx w/ chain and make some pem formatted outputs.  Output key is NOT encrypted

if [[ $# -lt 2 ]]; then
    echo "Usage: $(dirname $0 | sed -e 's/\.$//')$(basename $0) <PFX-in-file> <PFX-password> <Output-directory(Optional)>"
    printf "The output files will have the same prefix as the input PFX.\nNote: passwords should be single quoted if they have special characters.\n\n"
    exit 1
fi

IN="$1"
PASS="$2"
OUT_DIR=${3:-default}

if [ "$OUT_DIR" == "default" ]; then
    OUT_DIR=$(echo -n "$(pwd)/${1%.*}")
fi

echo "Output files will be saved to ${OUT_DIR}"

if [[ ! -d "$OUT_DIR" ]]; then
    echo "Creating ${OUT_DIR}"
    mkdir -p "$OUT_DIR"
else
    echo "${OUT_DIR} already exists.."
fi

## normalize OUT_DIR for concatination
OUT_DIR=$(echo -n "$OUT_DIR" | sed -e 's/\/$//')

N=$(echo -n ${IN} | sed -e 's/\.pfx//')
OUT_CERT="${OUT_DIR}/${N}.crt"
OUT_CHAIN="${OUT_DIR}/${N}.chain.crt"
OUT_KEY="${OUT_DIR}/${N}.key"
OUT_CA="${OUT_DIR}/${N}.ca.crt"

openssl pkcs12 -in "$IN" -nocerts -nodes -passin "pass:${PASS}" | sed -ne '/-BEGIN PRIVATE KEY-/,/-END PRIVATE KEY-/p' > "$OUT_KEY"
openssl pkcs12 -in "$IN" -clcerts -nokeys -passin "pass:${PASS}" | sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p' > "$OUT_CERT"
openssl pkcs12 -in "$IN" -cacerts -nokeys -chain -passin "pass:${PASS}" | sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p' > "$OUT_CA"

cat "$OUT_CERT" "$OUT_CA" > "$OUT_CHAIN"

## verify cert/key match, built in sanity check..
chk=$((openssl x509 -noout -modulus -in "$OUT_CHAIN"| openssl md5; openssl rsa -noout -modulus -in "$OUT_KEY" | openssl md5) | uniq)

echo ${#chk[@]}

if [ ${#chk[@]} == "1" ]; then
    echo "Cert and key match.."
    echo "$chk"
else
    echo "Cert and key no not match, something is wrong.."
    echo "$chk"
    exit 1
fi
