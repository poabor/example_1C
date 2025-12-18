#!/bin/bash
PATH_1C="/opt/1cv8/x86_64/8.3.27.1606"
dir_base="/mnt/NVME_512gb/localBases/erp_last"

"$PATH_1C/1cv8" DESIGNER /F "$dir_base" /NПолушкин /P159123 /Out ./build/tii_1.log /IBCheckAndRepair -LogAndRefsIntegrity -BadRefNone -BadDataNone