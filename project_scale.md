# Project Scale

This report measures the source scale of all 139 projects in the local CyberGym-E2E dataset.

The analysis uses one representative source snapshot per project.

The selected snapshot is the lexicographically first available `src.tgz` archive for that project.

`code_loc` is the number of source-code lines reported by `cloc`, excluding comments and blank lines.

`source_files` is the number of files recognized by `cloc`.

`repo_files` is the number of regular files under the main project source root after excluding common build and generated directories.

Bundled dependency trees are excluded from the project measurement.

## Summary

| Metric | Value |
|---|---:|
| Projects | 139 |
| Total code LOC | 65,493,632 |
| Total source files | 213,855 |
| Total repository files | 469,849 |
| Median code LOC | 170,878 |
| Median source files | 548 |

## Scale Bands

| Band | Code LOC range | Projects | Total code LOC | Source files |
|---|---:|---:|---:|---:|
| Tiny | Under 50,000 | 30 | 704,237 | 4,093 |
| Small | 50,000-199,999 | 47 | 5,390,089 | 21,794 |
| Medium | 200,000-499,999 | 24 | 7,156,098 | 25,302 |
| Large | 500,000-999,999 | 20 | 13,736,167 | 46,704 |
| Very large | 1,000,000 or more | 18 | 38,507,041 | 115,962 |

File-count bands use these ranges: Tiny under 100 source files, Small 100-499, Medium 500-1,499, Large 1,500-2,999, and Very large 3,000 or more.

## Project Table

| Project | Snapshot | Source root | Repository files | Source files | Code LOC | LOC scale | File scale |
|---|---|---|---:|---:|---:|---|---|
| `arduinojson` | `arvo_24633` | `arduinojson` | 409 | 375 | 29,855 | Tiny | Small |
| `arrow` | `arvo_24101` | `arrow` | 4,985 | 4,151 | 668,818 | Large | Very large |
| `assimp` | `arvo_24465` | `assimp` | 2,736 | 1,782 | 511,683 | Large | Large |
| `bind9` | `arvo_63186` | `bind9` | 4,672 | 1,790 | 387,784 | Medium | Large |
| `binutils` | `arvo_18615` | `binutils-gdb` | 34,041 | 28,929 | 6,653,419 | Very large | Very large |
| `boringssl` | `arvo_55556` | `boringssl` | 6,189 | 1,165 | 909,405 | Large | Medium |
| `botan` | `arvo_10628` | `botan` | 2,593 | 1,023 | 148,039 | Small | Medium |
| `c-blosc2` | `arvo_23717` | `c-blosc2` | 448 | 342 | 88,848 | Small | Small |
| `capstone` | `arvo_13466` | `capstonemaster capstonenext` | 36,988 | 1,337 | 267,400 | Medium | Medium |
| `clamav` | `arvo_23499` | `clamav-devel` | 2,833 | 2,264 | 649,482 | Large | Large |
| `cpython3` | `arvo_61721` | `cpython3` | 4,737 | 4,002 | 1,486,189 | Very large | Very large |
| `curl` | `arvo_66012` | `curl` | 3,861 | 1,963 | 275,276 | Medium | Large |
| `cyclonedds` | `arvo_51292` | `cyclonedds` | 1,194 | 975 | 257,334 | Medium | Medium |
| `dav1d` | `arvo_60432` | `dav1d` | 299 | 277 | 246,686 | Medium | Small |
| `duckdb` | `arvo_56682` | `duckdb` | 9,368 | 5,342 | 1,071,243 | Very large | Very large |
| `elfutils` | `arvo_42264` | `elfutils` | 1,449 | 998 | 157,782 | Small | Medium |
| `exiv2` | `arvo_45993` | `exiv2` | 1,758 | 632 | 371,600 | Medium | Medium |
| `faad2` | `arvo_58287` | `faad2` | 216 | 171 | 65,968 | Small | Small |
| `ffmpeg` | `oss-fuzz_368729566` | `ffmpeg` | 17,320 | 7,950 | 1,552,307 | Very large | Very large |
| `file` | `arvo_38393` | `file` | 526 | 70 | 18,079 | Tiny | Tiny |
| `flac` | `arvo_17069` | `flac` | 661 | 388 | 78,819 | Small | Small |
| `flatbuffers` | `arvo_46883` | `flatbuffers` | 1,319 | 1,099 | 185,090 | Small | Medium |
| `fluent-bit` | `arvo_26325` | `fluent-bit` | 4,178 | 3,461 | 994,505 | Large | Very large |
| `fmt` | `arvo_25884` | `fmt` | 193 | 177 | 58,718 | Small | Small |
| `freetype2` | `arvo_368` | `freetype2` | 723 | 636 | 159,137 | Small | Medium |
| `fribidi` | `arvo_34695` | `fribidi` | 133 | 100 | 10,401 | Tiny | Small |
| `gdal` | `arvo_4071` | `gdal` | 10,559 | 5,316 | 1,924,499 | Very large | Very large |
| `gdbm` | `arvo_38943` | `gdbm` | 169 | 111 | 17,110 | Tiny | Small |
| `ghostscript` | `arvo_42268` | `ghostpdl` | 6,281 | 4,138 | 1,816,816 | Very large | Very large |
| `glib` | `arvo_28458` | `glib` | 2,012 | 1,599 | 805,514 | Large | Large |
| `gpac` | `arvo_67043` | `gpac` | 9,035 | 1,679 | 864,089 | Large | Large |
| `gpsd` | `oss-fuzz_42537879` | `gpsd` | 1,335 | 507 | 215,011 | Medium | Medium |
| `gstreamer` | `arvo_53210` | `gstreamer` | 12,366 | 9,318 | 3,021,577 | Very large | Very large |
| `h2o` | `arvo_12096` | `h2o` | 5,648 | 1,917 | 502,597 | Large | Large |
| `h3` | `arvo_35902` | `h3` | 349 | 223 | 16,240 | Tiny | Small |
| `haproxy` | `oss-fuzz_415850462` | `haproxy` | 1,351 | 806 | 276,883 | Medium | Medium |
| `harfbuzz` | `arvo_11033` | `harfbuzz` | 1,119 | 327 | 72,921 | Small | Small |
| `hdf5` | `arvo_55214` | `hdf5` | 3,894 | 1,938 | 841,607 | Large | Large |
| `hiredis` | `arvo_28777` | `hiredis` | 67 | 60 | 10,664 | Tiny | Tiny |
| `hoextdown` | `arvo_23764` | `hoextdown` | 275 | 106 | 11,065 | Tiny | Small |
| `hostap` | `arvo_27269` | `hostap` | 1,415 | 1,095 | 544,850 | Large | Medium |
| `htslib` | `arvo_18152` | `htslib` | 301 | 145 | 52,736 | Small | Small |
| `hunspell` | `arvo_51102` | `hunspell` | 686 | 137 | 44,591 | Tiny | Small |
| `igraph` | `arvo_29408` | `igraph` | 1,851 | 1,397 | 247,386 | Medium | Medium |
| `imagemagick` | `arvo_5710` | `imagemagick` | 2,425 | 1,637 | 569,317 | Large | Large |
| `irssi` | `arvo_31491` | `irssi` | 666 | 483 | 71,319 | Small | Small |
| `jq` | `arvo_64574` | `jq` | 485 | 277 | 146,851 | Small | Small |
| `json-c` | `arvo_23619` | `json-c` | 186 | 125 | 12,525 | Tiny | Small |
| `jsoncpp` | `arvo_18140` | `jsoncpp` | 236 | 165 | 11,881 | Tiny | Small |
| `kamailio` | `arvo_38050` | `kamailio` | 6,574 | 5,051 | 1,057,297 | Very large | Very large |
| `kmime` | `oss-fuzz_441263171` | `kmime` | 183 | 148 | 16,854 | Tiny | Small |
| `lcms` | `arvo_42227` | `lcms` | 267 | 138 | 92,661 | Small | Small |
| `leptonica` | `arvo_21435` | `leptonica` | 885 | 538 | 199,914 | Small | Medium |
| `libaom` | `arvo_10574` | `aom` | 960 | 917 | 357,127 | Medium | Medium |
| `libarchive` | `arvo_38751` | `libarchive` | 1,096 | 661 | 164,616 | Small | Medium |
| `libavc` | `arvo_27856` | `libavc` | 340 | 328 | 124,387 | Small | Small |
| `libbpf` | `arvo_40317` | `libbpf` | 108 | 91 | 108,141 | Small | Tiny |
| `libcoap` | `arvo_26371` | `libcoap` | 323 | 198 | 47,317 | Tiny | Small |
| `libconfig` | `oss-fuzz_391975647` | `libconfig` | 258 | 126 | 48,763 | Tiny | Small |
| `libdwarf` | `arvo_40674` | `libdwarf` | 477 | 347 | 139,888 | Small | Small |
| `libexif` | `arvo_37211` | `libexif` | 194 | 138 | 86,069 | Small | Small |
| `libgit2` | `arvo_11167` | `libgit2` | 6,015 | 967 | 183,230 | Small | Medium |
| `libheif` | `arvo_22094` | `libheif` | 160 | 120 | 38,233 | Tiny | Small |
| `libhevc` | `arvo_23197` | `libhevc` | 558 | 548 | 252,969 | Medium | Medium |
| `libical` | `arvo_47986` | `libical` | 1,112 | 371 | 87,439 | Small | Small |
| `libidn2` | `arvo_12420` | `libidn2` | 10,922 | 4,608 | 576,318 | Large | Very large |
| `libjpeg-turbo` | `arvo_33340` | `libjpeg-turbo` | 517 | 422 | 112,835 | Small | Small |
| `libjxl` | `oss-fuzz_432441297` | `libjxl` | 4,145 | 2,653 | 759,094 | Large | Large |
| `liblouis` | `arvo_60723` | `liblouis` | 1,034 | 538 | 1,488,492 | Very large | Medium |
| `libpcap` | `arvo_48863` | `libpcap` | 330 | 205 | 68,994 | Small | Small |
| `libphonenumber` | `oss-fuzz_413161357` | `libphonenumber` | 3,751 | 461 | 172,930 | Small | Small |
| `libplist` | `arvo_44089` | `libplist` | 227 | 86 | 10,570 | Tiny | Tiny |
| `libraw` | `arvo_42108` | `libraw` | 398 | 175 | 106,275 | Small | Small |
| `librawspeed` | `arvo_3012` | `librawspeed` | 267 | 247 | 32,145 | Tiny | Small |
| `libsndfile` | `arvo_25364` | `libsndfile` | 361 | 305 | 66,567 | Small | Small |
| `libspectre` | `arvo_21302` | `libspectre` | 5,333 | 3,552 | 1,831,430 | Very large | Very large |
| `libspng` | `arvo_14935` | `libspng` | 242 | 27 | 4,419 | Tiny | Tiny |
| `libssh` | `arvo_10486` | `libssh` | 333 | 273 | 61,871 | Small | Small |
| `libssh2` | `arvo_29769` | `libssh2` | 429 | 191 | 49,158 | Tiny | Small |
| `libtpms` | `arvo_65530` | `libtpms` | 1,572 | 541 | 116,328 | Small | Medium |
| `libultrahdr` | `oss-fuzz_42535447` | `libultrahdr` | 757 | 621 | 156,543 | Small | Medium |
| `libvips` | `arvo_39481` | `libvips` | 814 | 667 | 190,422 | Small | Medium |
| `libwebp` | `oss-fuzz_382816119` | `libwebp` | 344 | 302 | 91,591 | Small | Small |
| `libwebsockets` | `arvo_48959` | `libwebsockets` | 1,899 | 1,611 | 370,120 | Medium | Large |
| `libxaac` | `arvo_61691` | `libxaac` | 757 | 737 | 243,183 | Medium | Medium |
| `libxml2` | `arvo_23765` | `libxml2` | 4,618 | 1,633 | 456,976 | Medium | Large |
| `libxslt` | `arvo_57061` | `libxslt` | 2,183 | 1,372 | 194,478 | Small | Medium |
| `lldpd` | `arvo_52006` | `lldpd` | 633 | 450 | 170,878 | Small | Small |
| `lua` | `arvo_31541` | `lua` | 111 | 105 | 33,236 | Tiny | Small |
| `mapserver` | `arvo_52066` | `MapServer` | 4,390 | 1,851 | 389,850 | Medium | Large |
| `matio` | `oss-fuzz_407185361` | `matio` | 530 | 117 | 35,067 | Tiny | Small |
| `md4c` | `arvo_31332` | `md4c` | 50 | 32 | 9,210 | Tiny | Tiny |
| `miniz` | `arvo_26682` | `miniz` | 34 | 30 | 10,066 | Tiny | Tiny |
| `mongoose` | `arvo_51757` | `mongoose` | 469 | 433 | 111,039 | Small | Small |
| `mosquitto` | `arvo_55820` | `mosquitto` | 1,517 | 1,285 | 131,987 | Small | Medium |
| `mruby` | `arvo_18756` | `mruby` | 402 | 384 | 72,334 | Small | Small |
| `mupdf` | `arvo_46541` | `mupdf` | 11,671 | 5,734 | 1,747,129 | Very large | Very large |
| `net-snmp` | `arvo_36908` | `net-snmp` | 3,376 | 1,896 | 428,676 | Medium | Large |
| `ntopng` | `arvo_60037` | `ntopng` | 6,790 | 4,896 | 565,386 | Large | Very large |
| `oatpp` | `oss-fuzz_391916478` | `oatpp` | 467 | 464 | 39,050 | Tiny | Small |
| `open62541` | `arvo_39741` | `open62541` | 3,329 | 744 | 1,758,379 | Very large | Medium |
| `openexr` | `arvo_46309` | `openexr` | 826 | 721 | 232,139 | Medium | Medium |
| `openjpeg` | `arvo_18979` | `openjpeg` | 1,824 | 525 | 205,021 | Medium | Medium |
| `opensc` | `arvo_18482` | `opensc` | 544 | 419 | 176,602 | Small | Small |
| `opensips` | `arvo_39802` | `opensips` | 5,925 | 4,415 | 2,063,107 | Very large | Very large |
| `openssl` | `arvo_17715` | `openssl` | 27,800 | 5,261 | 1,329,480 | Very large | Very large |
| `openthread` | `oss-fuzz_411460530` | `openthread` | 3,903 | 2,693 | 543,171 | Large | Large |
| `p11-kit` | `arvo_31276` | `p11-kit` | 563 | 356 | 80,245 | Small | Small |
| `pcapplusplus` | `arvo_43408` | `PcapPlusPlus` | 971 | 423 | 68,386 | Small | Small |
| `pcre2` | `arvo_67297` | `pcre2` | 466 | 208 | 126,067 | Small | Small |
| `php` | `arvo_42894` | `php-src` | 20,865 | 2,567 | 942,333 | Large | Large |
| `qpdf` | `oss-fuzz_42535152` | `qpdf` | 2,886 | 794 | 106,421 | Small | Medium |
| `quickjs` | `arvo_46957` | `quickjs` | 62 | 50 | 83,278 | Small | Tiny |
| `radare2` | `arvo_13704` | `radare2` | 2,759 | 2,350 | 670,891 | Large | Large |
| `readstat` | `arvo_12662` | `readstat` | 666 | 168 | 30,681 | Tiny | Small |
| `selinux` | `arvo_36611` | `selinux` | 1,628 | 855 | 503,055 | Large | Medium |
| `skcms` | `arvo_6521` | `skcms` | 88 | 24 | 3,518 | Tiny | Tiny |
| `sleuthkit` | `arvo_36025` | `sleuthkit` | 890 | 683 | 240,344 | Medium | Medium |
| `spice-usbredir` | `arvo_36861` | `spice-usbredir` | 44 | 34 | 8,445 | Tiny | Tiny |
| `sudoers` | `arvo_30236` | `sudo` | 1,049 | 558 | 223,887 | Medium | Medium |
| `swift-protobuf` | `oss-fuzz_42534949` | `swift-protobuf` | 673 | 619 | 439,526 | Medium | Medium |
| `tinygltf` | `arvo_42123` | `tinygltf` | 1,339 | 1,214 | 309,986 | Medium | Medium |
| `tinysparql` | `oss-fuzz_396460492` | `tinysparql` | 2,204 | 445 | 112,797 | Small | Small |
| `unit` | `oss-fuzz_42536348` | `unit` | 1,207 | 895 | 140,965 | Small | Medium |
| `upx` | `arvo_65510` | `upx` | 890 | 726 | 204,944 | Medium | Medium |
| `uriparser` | `oss-fuzz_389731913` | `uriparser` | 71 | 52 | 16,250 | Tiny | Tiny |
| `util-linux` | `arvo_53149` | `util-linux` | 2,820 | 1,048 | 770,812 | Large | Medium |
| `uwebsockets` | `arvo_19757` | `uWebSockets` | 35,646 | 1,625 | 1,339,774 | Very large | Large |
| `wamr` | `oss-fuzz_404921047` | `wamr` | 1,844 | 1,379 | 255,990 | Medium | Medium |
| `wasm3` | `arvo_33318` | `wasm3` | 313 | 210 | 25,340 | Tiny | Small |
| `wavpack` | `arvo_20060` | `wavpack` | 182 | 145 | 50,171 | Small | Small |
| `wireshark` | `arvo_1236` | `wireshark` | 9,858 | 4,784 | 3,845,736 | Very large | Very large |
| `wolfmqtt` | `arvo_30181` | `wolfmqtt` | 127 | 104 | 21,740 | Tiny | Small |
| `wolfssl` | `oss-fuzz_442261624` | `wolfssl` | 3,227 | 1,953 | 2,151,855 | Very large | Large |
| `wt` | `oss-fuzz_370689421` | `wt` | 3,008 | 2,346 | 543,240 | Large | Large |
| `yara` | `arvo_11945` | `yara` | 260 | 164 | 51,607 | Small | Small |
| `zeek` | `arvo_55430` | `zeek` | 30,703 | 17,310 | 2,368,312 | Very large | Very large |
| `zlib` | `arvo_49903` | `zlib` | 247 | 138 | 41,764 | Tiny | Small |
| `zstd` | `arvo_16445` | `zstd` | 419 | 354 | 95,905 | Small | Small |
