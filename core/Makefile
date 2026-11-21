# Builds the mech_core shared library next to this Makefile.
#   Linux / Docker: libmech_core.so
#   Windows (msys2 g++): mech_core.dll
CXX ?= g++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra -Wno-unused-parameter
SRCS := map.cpp los.cpp nav.cpp aim.cpp
HDRS := mech_core.h internal.h

ifeq ($(OS),Windows_NT)
TARGET := mech_core.dll
LDFLAGS += -shared -static -static-libstdc++ -static-libgcc
else
TARGET := libmech_core.so
CXXFLAGS += -fPIC -fvisibility=hidden
LDFLAGS += -shared -static-libstdc++ -static-libgcc
endif

all: $(TARGET)

$(TARGET): $(SRCS) $(HDRS)
	$(CXX) $(CXXFLAGS) $(SRCS) -o $@ $(LDFLAGS)

clean:
	rm -f libmech_core.so mech_core.dll

.PHONY: all clean
