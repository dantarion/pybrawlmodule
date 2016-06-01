import os, struct,subprocess,io
from operator import itemgetter, attrgetter
def readStringAt(loc,f):
    f.seek(loc)
    s = ""
    c = f.read(1)
    while len(c) == 1 and ord(c) != 0:
        s = s+c
        c = f.read(1)
    return s
BLOCKNAMES = ["0","ASM","Init","Final","Constants","Objects","Other"]
class RelCommand:
    def __init__(self,f=0):
        self.Internal = 0
        self.File = 0
        self.Comment = ""
        if f:
            data = struct.unpack(">HBBI",f.read(8))
            
            self.Inc = data[0]
            self.Command = data[1]
            self.TargetBlockIndex = data[2]
            self.Operand = data[3]
            self.File = 1
            
    def __str__(self):
        if self.Internal and self.Block != 1 and self.TargetBlockIndex == 1 and self.TargetModuleID == 0x1B:
            return "sora_ASMRel @%08X ID%03X C%02X" % (self.Operand+0x8070aa14,self.Index,self.Command)
        elif self.Internal and self.Block != 1 and self.TargetBlockIndex == 1:
            return "ASMRel @%06X ID%03X C%02X" % (self.Offset,self.Index,self.Command)  
        elif self.Internal and self.Block == 1 and self.TargetBlockIndex == 1:
            return "ASMRel +%d ID%03X C%02X" % (self.Offset&3,self.Index,self.Command)
        elif self.Block == 1 and self.File:
            return "Rel +%d C%02X M%02X B%02X @%06X" % (self.Offset&3,self.Command,self.TargetModuleID,self.TargetBlockIndex,self.Operand)
        else:
            return "Rel @%06X C%02X M%02X B%02X @%06X" % (self.Offset,self.Command,self.TargetModuleID,self.TargetBlockIndex,self.Operand)
startupinfo = None
if os.name == 'nt':
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
class RelBlock:
    def RelAt(self,off):
        ptrRell = filter(lambda rel: off == rel.Offset and rel.Block == self.Index, self.RelFile.Rels)
        if len(ptrRell) == 0:
                return None
        return ptrRell[0]
    def strat(self,off):
        strlen = 0
        while ord(self.Data[off+strlen]) != 0:
                strlen +=1
        return self.Data[off:off+strlen]
    def dumpData(self,asm=1):
        if len(BLOCKNAMES) > self.Index:
            name = BLOCKNAMES[self.Index]
        else:
            name = "Unk%02d" % self.Index
        if self.Offset == 0:
            return

        out = open("working/"+name+".raw","wb")
        
        out.write(self.Data)
        out.close()
        if self.Index == 1 and asm:
            #run vdappc on the raw output
            working = open("tmp.out","wb")
            subprocess.Popen("vdappc.exe working/"+name+".raw 0", stdout=working,stderr=subprocess.PIPE, startupinfo=startupinfo).communicate()
            working.close()
            working = open("tmp.out","rb")
            c = open("working/"+name+".asm","wb")
            working.seek(0)
            rels = filter(lambda rel: self.Index == rel.Block,self.RelFile.Rels)
            targetrels = filter(lambda rel: self.RelFile.FileID == rel.TargetModuleID and self.Index == rel.TargetBlockIndex,self.RelFile.Rels)
            target = float(self.Size/20)
            offset = 0
            RAWData = working.read().split("\n")
            processed = []
            for data in RAWData:
                 if offset > target:
                     print float(offset)/self.Size,
                     target = target+self.Size/20
                 #print hex(offset)
                 data = data[20:-1]#drop newline
                 if data.find("0x") != -1:
                     tmpindex = data.find("0x")
                     staticoff = int(data[tmpindex:],16)
                     data = data[0:tmpindex] + hex(staticoff-offset)
                 
                 processed.append(data)
                 offset = offset+4
            for thing in ["GetSrc","Init","Finalize"]:
                index = self.RelFile.__dict__[thing] & 0xFFFFFFFC
                processed[index/4] = processed[index/4]+"#"+thing    
            for rel in rels:
                index = rel.Offset & 0xFFFFFFFC
                processed[index/4] = processed[index/4]+"#"+str(rel)
            for rel in targetrels:
                index = rel.Operand & 0xFFFFFFFC
                processed[index/4] = processed[index/4]+"#Target %03X"%rel.Index
                if rel.Comment != "":
                    processed[index/4] = "".join(["#\n#",rel.Comment," @", hex(index),"\n#\n",processed[index/4]])
            for s in processed:
                c.write(s)
                c.write("\n")
            c.close()
        elif self.Index != 1:
            out = open("working/"+name+".txt","wb")
            for rel in sorted(self.RelFile.Rels, key=attrgetter('Offset')):
                if self.Index == rel.Block:
                    out.write(str(rel)+"\n")
    def __str__(self):
        global BLOCKNAMES
        if len(BLOCKNAMES) > self.Index:
            name = BLOCKNAMES[self.Index]
        else:
            name = "Unk%02d" % self.Index
        return "%10s - Flags %d, Start %X - Size %X - End %X"%(name,self.Flags,self.Offset,self.Size,self.Offset+self.Size)
    pass
def compileFile(filename):
    output = subprocess.Popen(["powerpc-gekko-as.exe", "-mregnames", "-mgekko", "-o","tmp.o", filename], stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, startupinfo=startupinfo).communicate()
    subprocess.call(["powerpc-gekko-objcopy.exe", "-O", "binary", 
        "tmp.o", filename.replace(".asm",".raw")], stderr=subprocess.PIPE, startupinfo=startupinfo)
    print "Compiled",filename,"into ",filename.replace(".asm",".raw")
class RelFile:
    def readBlocks(self):
        self.Rels = []
        newBlocks = []
        modulerefs = []
        fullrels = []
        asmrels = {}
        targets = {}
        for block in self.Blocks:
            if block.Index == 1:
                offset = 0
                compileFile("working/ASM.asm")
                tmp = open("working/ASM.raw","rb")
                block.Data = tmp.read()
                tmp.close()
                for line in open("working/ASM.asm","r"):
                    line = line[0:-1]#strip newline
                    if len(line) == 0 or line[0] == "#" or line[0]== " ":
                        print line
                        continue
                    data = line.split("#")
                    for i in range(1,len(data)):
                        cur = data[i]
                        params = cur.split(" ")
                        if cur in ["GetSrc","Init","Finalize"]:
                            self.__dict__[cur] = offset
                        elif params[0] == "ASMRel":
                            reldata = RelCommand()
                            reldata.Offset = offset+int(params[1][1])
                            reldata.Command = int(params[3][1:],16)
                            reldata.TargetModuleID = self.FileID
                            reldata.Block = block.Index
                            reldata.TargetBlockIndex = block.Index
                            asmrels[int(params[2][2:],16)] = reldata
                        elif params[0] == "Rel":
                            reldata = RelCommand()
                            reldata.Offset = offset+int(params[1][1])
                            reldata.Command = int(params[2][1:],16)
                            reldata.TargetModuleID = int(params[3][1:],16)
                            reldata.Block = block.Index
                            reldata.TargetBlockIndex = int(params[4][1:],16)
                            reldata.Operand = int(params[5][1:],16)
                            fullrels.append(reldata)
                        elif params[0] == "Target":
                            targets[int(params[1],16)] = offset
                        else:
                            print hex(offset),params
                    offset +=4
            else:
                if block.Offset == 0:
                    continue
                tmp = open("working/"+block.Name+".raw","rb")
                block.Data = tmp.read()
                tmp.close()
                for line in open("working/"+block.Name+".txt","r"):
                    line = line[0:-1]#strip newline
                    params = line.split(" ")
                    if params[0] == "ASMRel":
                            reldata = RelCommand()
                            reldata.Offset = int(params[1][1:],16)
                            reldata.Command = int(params[3][1:],16)
                            reldata.TargetModuleID = self.FileID
                            reldata.Block = block.Index
                            reldata.TargetBlockIndex = 1
                            asmrels[int(params[2][2:],16)] = reldata
                    elif params[0] == "Rel":
                            reldata = RelCommand()
                            reldata.Offset = int(params[1][1:],16)
                            reldata.Command = int(params[2][1:],16)
                            reldata.TargetModuleID = int(params[3][1:],16)
                            reldata.Block = block.Index
                            reldata.TargetBlockIndex = int(params[4][1:],16)
                            reldata.Operand = int(params[5][1:],16)
                            fullrels.append(reldata)
                    else:
                        print params
        #all blocks loaded, process rels
        for key,arel in asmrels.items():
            if key not in targets:
                raise Exception("NO TARGET FOUND FOR KEY %03X"%key)
            arel.Operand = targets[key]
            fullrels.append(arel)
 
        truerelist = sorted(sorted(sorted(fullrels, key=attrgetter('Offset')), key=attrgetter('Block')), key=attrgetter('TargetModuleID'))
        self.Rels = truerelist
    def toFile(self,filename):
        f = open(filename,"wb")
        f.seek(0x4C)
        curoff = 0x4C+self.BlockCount*8
        for block in self.Blocks:
            if block.Offset != 0:
                f.write(struct.pack(">I",curoff|block.Flags))
                print block.Index,block.Offset-curoff,len(block.Data)
            else:
                f.write(struct.pack(">I",0|block.Flags))
                
            f.write(struct.pack(">I",len(block.Data)))
            if block.Offset != 0:
                curoff += len(block.Data)
            if block.Index == 4:
                curoff += 12
            
            
        for block in self.Blocks:
            if block.Offset != 0:
                f.write(block.Data)
            if block.Index == 4:
                f.seek(12,1)
        #Build Proper RelLists (per referenced module
        RelLists = {}
        currentMod = self.Rels[0].TargetModuleID
        currentBlock = -1
        previousOff = 0
        for rel in self.Rels:
            if rel.TargetModuleID != currentMod:
                RelLists[currentMod] += struct.pack(">HBBI",0,0xCB,0,0)
                currentMod = rel.TargetModuleID
                print "CB COMMAND",hex(currentMod)
                currentBlock = -1
            if rel.Block != currentBlock:
                if currentMod not in RelLists:
                    RelLists[currentMod] = ""
                RelLists[currentMod] += struct.pack(">HBBI",0,0xCA,rel.Block,0)
                currentBlock = rel.Block
                print "CA COMMAND",hex(currentBlock)
                previousOff = 0

                previousOff = 0
            #print rel
            RelLists[currentMod] += struct.pack(">HBBI",rel.Offset-previousOff,rel.Command,rel.TargetBlockIndex,rel.Operand)
            previousOff = rel.Offset
        #end the last list
        RelLists[currentMod] += struct.pack(">HBBI",0,0xCB,0,0)
        #writeRelLists
        curoff = f.tell()+len(RelLists)*8
        #proper order
        modlist = []
        for k in RelLists.keys():
            if k == 0:
                continue
            else:
                modlist.append(k)
        modlist = sorted(modlist)
        modlist.append(0)
        self.RelList = f.tell()
        for k in modlist:  
            print "writing relist for module %02X at %X" % (k,curoff)
            if k == self.FileID:
                self.RelDataSelf == curoff
            f.write(struct.pack(">I",k))
            
            f.write(struct.pack(">I",curoff))
            curoff += len(RelLists[k])
        self.RelData = f.tell()
        for k in modlist:
            f.write(RelLists[k])
           
            
        
        f.seek(0)
        f.write(struct.pack(">I",self.FileID))
        f.write(struct.pack(">I",self.PrevEntry))
        f.write(struct.pack(">I",self.NextEntry))
        f.write(struct.pack(">I",self.BlockCount))

        f.write(struct.pack(">I",self.BlockTable))
        f.write(struct.pack(">I",self.NameOffset))
        f.write(struct.pack(">I",self.NameSize))
        f.write(struct.pack(">I",self.Version))

        f.write(struct.pack(">I",self.BSSSize))
        f.write(struct.pack(">I",self.RelData))
        f.write(struct.pack(">I",self.RelList))
        f.write(struct.pack(">I",self.RelListSize))

        f.write(struct.pack(">B",self.ConstructorIndex))
        f.write(struct.pack(">B",self.DestructorIndex))
        f.write(struct.pack(">B",self.GetSrcIndex))
        f.write(struct.pack(">B",self.Last))

        f.write(struct.pack(">I",self.Init))
        f.write(struct.pack(">I",self.Finalize))
        f.write(struct.pack(">I",self.GetSrc))
        f.write(struct.pack(">I",self.Align))

        f.write(struct.pack(">I",self.BSSAlign))
        f.write(struct.pack(">I",self.RelDataSelf))
        f.close()

        

    def __init__(self,filename):
        global CUR_REL
        f = open(filename,"rb")
        self.FileID = struct.unpack(">I",f.read(4))[0]
        self.PrevEntry = struct.unpack(">I",f.read(4))[0]
        self.NextEntry = struct.unpack(">I",f.read(4))[0]
        self.BlockCount = struct.unpack(">I",f.read(4))[0]
        
        self.BlockTable = struct.unpack(">I",f.read(4))[0]
        self.NameOffset = struct.unpack(">I",f.read(4))[0]
        self.NameSize = struct.unpack(">I",f.read(4))[0]
        self.Version = struct.unpack(">I",f.read(4))[0]
        
        self.BSSSize = struct.unpack(">I",f.read(4))[0]
        self.RelData = struct.unpack(">I",f.read(4))[0]
        self.RelList = struct.unpack(">I",f.read(4))[0]
        self.RelListSize = struct.unpack(">I",f.read(4))[0]
        
        self.ConstructorIndex = struct.unpack(">B",f.read(1))[0]
        self.DestructorIndex = struct.unpack(">B",f.read(1))[0]
        self.GetSrcIndex = struct.unpack(">B",f.read(1))[0]
        self.Last = struct.unpack(">B",f.read(1))[0]
        
        self.Init = struct.unpack(">I",f.read(4))[0]
        self.Finalize = struct.unpack(">I",f.read(4))[0]
        self.GetSrc = struct.unpack(">I",f.read(4))[0]
        self.Align = struct.unpack(">I",f.read(4))[0]
        
        self.BSSAlign = struct.unpack(">I",f.read(4))[0]
        self.RelDataSelf = struct.unpack(">I",f.read(4))[0]
        
        self.Blocks = []
        for i,v in self.__dict__.items():
            print i,v
        print hex(f.tell())
        #Read in blocks
        f.seek(self.BlockTable)
        for i in range(0,self.BlockCount):
            f.seek(self.BlockTable+i*8)
            relblock = RelBlock() 
            relblock.RelFile = self
            relblock.Index = i
            if len(BLOCKNAMES) > relblock.Index:
                relblock.Name = BLOCKNAMES[relblock.Index]
            else:
                relblock.Name = "Unk%02d" % relblock.Index
            tmp = struct.unpack(">I",f.read(4))[0]
            relblock.Offset = tmp  & ~0x03
            relblock.Comments = {}
            relblock.Size = struct.unpack(">I",f.read(4))[0]
            relblock.Flags = tmp & 0x03
            f.seek(relblock.Offset)
            relblock.Data = f.read(relblock.Size)
            print relblock
            self.Blocks.append(relblock)
        #RelLists
        self.Rels = []
        index = 0
        for i in range(0,self.RelListSize/8):
            f.seek(self.RelList+i*8)
            ID =  struct.unpack(">I",f.read(4))[0]
            FileOffset = struct.unpack(">I",f.read(4))[0]
            print "Reading RelList->%02X @%X" % (ID,FileOffset)
            f.seek(FileOffset)
            cmd = RelCommand(f)
            while cmd.Command != 0xCB:#CB Command ends a list
                if cmd.Command == 0xCA:#CA Command switches block
                    offset = 0
                    curBlock = cmd.TargetBlockIndex
                else:
                    offset += cmd.Inc
                    cmd.Offset = offset
                    cmd.TargetModuleID = ID
                    
                    if self.FileID == ID:
                        cmd.Internal = 1
                        cmd.Index = index
                        index = index+1
                    cmd.Block = curBlock
                    if curBlock == 2:
                        cmd.Comment = "InitBlock[%02d]" % (cmd.Offset/4)
                    if curBlock == 3:
                        cmd.Comment = "FinalBlock[%02d]" % (cmd.Offset/4)
                    #print cmd
                    
                    self.Rels.append(cmd)
                cmd = RelCommand(f)
    def dumpBlocks(self):
        for block in self.Blocks:
            print "Dumping...",block
            block.dumpData()
    def dumpFunctions(self):
        log = open("working/funcdata.txt","w")
        objblock = self.Blocks[5]
        objrels = filter(lambda rel: rel.Command == 1 and self.FileID == rel.TargetModuleID and 5 == rel.TargetBlockIndex and rel.Block == 5,self.Rels)
        it = iter(self.Rels)
        commandindex = 0
        Types = {}
        inher = []
        ic = 0
        for rel in objrels:
            ic = ic + 1
            if rel in inher:
                continue
            print ic,len(objrels)
            ptrblock = objblock.RelAt(rel.Operand)
            if ptrblock == None:
                continue
            s = objblock.strat(ptrblock.Operand)
            if len(s) == 0:
                continue
            SCOPE = struct.unpack_from(">i",objblock.Data,rel.Offset+4)[0]
            #iterate through inheritances
            if s not in Types:
                Types[s] = {}
                Types[s][0] = "null"
                inheritptr = objblock.RelAt(ptrblock.Offset+4)
                inherit = None
                if inheritptr != None:
                    inherit =  objblock.RelAt(inheritptr.Operand)
                #this points to a rel that points to a delaration
                bs = "unk"
                while inherit != None:
                    inher.append(inherit)
                    inheractual = objblock.RelAt(inherit.Operand)#this points to the declaration
                    TARGET_SCOPE = struct.unpack_from(">i",objblock.Data,inherit.Offset+4)[0]
                    Types[s][TARGET_SCOPE] = objblock.strat(inheractual.Operand)
                    inherit = objblock.RelAt(inherit.Offset+8)
            #print sorted(Types[s].keys())
            if -SCOPE in Types[s]:
                bs = Types[s][-SCOPE]
            else:
                bs = "null"
            func = objblock.RelAt(rel.Offset+8)
            i = 0
            log.write(hex(rel.Offset)+" ")
            log.write(s+"->"+bs)
            log.write("#"+str(SCOPE/4)+"\n")
            while func != None and func.TargetBlockIndex != 5:
                log.write("\t[%02d] %s \n"%(i,func))
                log.flush()
                func.Comment = "%s:%s[%d]" % (s,bs,i)
                i += 1
                func = objblock.RelAt(func.Offset+4)
        log.close()
    def dumpObjects(self):
        log = open("working/classdata.txt","w")
        objblock = self.Blocks[5]
        objrels = filter(lambda rel: self.FileID == rel.TargetModuleID and 5 == rel.TargetBlockIndex and rel.Block != 5,self.Rels)
        it = iter(self.Rels)
        commandindex = 0
        for rel in it:
            if rel.Command != 1 or self.FileID != rel.TargetModuleID or 5 != rel.Block:
                continue
            commandindex = 0
            if 5 != rel.TargetBlockIndex:
                continue
                
            s = objblock.strat(rel.Operand)
            if len(s) == 0:
                continue
            log.write(str(rel)+"\n")
            log.write(s+"\n")
            ptrrel = it.next()
            curOff = ptrrel.Operand
            startOff =  rel.Offset
            while curOff < startOff:
                curRel = objblock.RelAt(curOff)
                curOff += 8
                if curRel == None:
                    log.write("No rel@%X\n"%curOff)
                    break
                curRel = objblock.RelAt(curRel.Operand)
                #print curRel
                if curRel == None:
                    continue
                log.write("-"+objblock.strat(curRel.Operand)+"\n")
                 
            log.write("\n")
        log.close()
def somescriptfunc():
    # does something
    rel = RelFile("M:/ProjectM/extracted_ntsc/module/sora_melee.rel")
    #rel.toFile("orig.rel")
    rel.dumpFunctions()
    rel.dumpBlocks()
    #rel.dumpObjects()
    #rel.readBlocks()
    
    
    rel.toFile("out.rel")
    #compileFile("working/ASM.asm")


if __name__ == "__main__":
    # do something if this script is invoked
    # as python scriptname. Otherwise, gets ignored.

    import cProfile
    #cProfile.run('somescriptfunc()')
    somescriptfunc()


#sys.stdout = open("log.txt","wb")

