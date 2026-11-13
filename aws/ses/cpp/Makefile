# pskit's Amazon SES compatible server, C++17 + OpenSSL.
#   make                      build $(BUILD)/ses-server (default build/)
#   make BUILD=/data/.build   build elsewhere (start.sh does this in the container)
#   make clean
# Override CXX, CPPFLAGS, LDFLAGS for a toolchain or OpenSSL outside the system paths.

CXX      ?= g++
BUILD    ?= build
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra
CPPFLAGS ?=
LDFLAGS  ?=
LDLIBS   ?= -lssl -lcrypto -lpthread

SRC  := $(wildcard src/*.cpp)
OBJ  := $(patsubst src/%.cpp,$(BUILD)/obj/%.o,$(SRC))
DEPS := $(OBJ:.o=.d)

all: $(BUILD)/ses-server

$(BUILD)/ses-server: $(OBJ)
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $(OBJ) $(LDLIBS)

$(BUILD)/obj/%.o: src/%.cpp | $(BUILD)/obj
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -MMD -MP -c -o $@ $<

$(BUILD)/obj:
	mkdir -p $@

clean:
	rm -rf $(BUILD)

-include $(DEPS)

.PHONY: all clean
