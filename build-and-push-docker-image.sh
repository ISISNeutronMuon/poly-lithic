# set build time variables
export BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
export VCS_REF=$(git rev-parse --short HEAD)
export VERSION=$(hatch version)

# # if build-info file exists, remove it
# if [ -f build-info ]; then
#     rm build-info.json

# # # create build-info file
# touch build-info.json
# echo "{" >> build-info.json
# echo "  \"build-date\": \"$BUILD_DATE\"," >> build-info.json
# echo "  \"vcs-ref\": \"$VCS_REF\"" >> build-info.json
# echo "}" >> build-info.json

docker build --pull --rm --target vanilla -f "Dockerfile" -t harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:base-$VERSION "."
docker build --pull --rm --target torch -f "Dockerfile" -t harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:torch-$VERSION "."
docker build --pull --rm --target tensorflow -f "Dockerfile" -t harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:tensorflow-$VERSION "."

# docker push harbor.stfc.ac.uk/isis-accelerator-controls/lume-deploy:dev13

# docker build --pull --rm -f "Dockerfile.interactive" -t harbor.stfc.ac.uk/isis-accelerator-controls/lume-deploy:interactive13 "." &&
# docker push harbor.stfc.ac.uk/isis-accelerator-controls/lume-deploy:interactive13

# docker push harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:base-$VERSION
# docker push harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:torch-$VERSION
# docker push harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:tensorflow-$VERSION

# docker hub retag and push isisacceleratorcontrols/poly-lithic
docker tag harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:base-$VERSION isisacceleratorcontrols/poly-lithic:base-$VERSION
docker tag harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:torch-$VERSION isisacceleratorcontrols/poly-lithic:torch-$VERSION
docker tag harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:tensorflow-$VERSION isisacceleratorcontrols/poly-lithic:tensorflow-$VERSION

docker push isisacceleratorcontrols/poly-lithic:base-$VERSION
docker push isisacceleratorcontrols/poly-lithic:torch-$VERSION
docker push isisacceleratorcontrols/poly-lithic:tensorflow-$VERSION

# if version does not containe a 'dev'or tag, then push to latest
if [[ $VERSION != *"dev"* ]]; then

    # tag latest versions
    docker tag harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:base-$VERSION harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:base-latest
    docker tag harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:torch-$VERSION harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:torch-latest
    docker tag harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:tensorflow-$VERSION harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:tensorflow-latest
    
    # push latest tags
    docker push harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:base-latest
    docker push harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:torch-latest
    docker push harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:tensorflow-latest

    # also tag and push latest base as latest
    docker tag harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:base-latest harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:latest
    docker push harbor.stfc.ac.uk/isis-accelerator-controls/poly-lithic:latest
