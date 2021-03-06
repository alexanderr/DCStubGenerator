from pandac.PandaModules import DCFile, loadPrcFile, ConfigVariableBool
import os
import re


CLASS_DELIMITERS = [
    'AI',
    'UD',
    'OV'
]

IMPORTS = {
    # Imports not included in the root folder go here.
    'DistributedObject': 'direct.distributed',
    'DistributedSmoothNode': 'direct.distributed',
    'DistributedObjectGlobal': 'direct.distributed',
}

INDENT = '    '


class DCStubGenerator:
    def __init__(self, configFile):
        loadPrcFile(configFile)
        self.ignoreTypes = {
            '': ConfigVariableBool('ignore-client', True).getValue(),
            'AI': ConfigVariableBool('ignore-AI', False).getValue(),
            'UD': ConfigVariableBool('ignore-UD', False).getValue(),
            'OV': ConfigVariableBool('ignore-OV', True).getValue()
        }
        self.wantOverwrite = ConfigVariableBool('overwrite-files', False).getValue()
        self.generateNonImportDclasses = ConfigVariableBool('generate-non-import-dclasses', False).getValue()
        self.wantInit = ConfigVariableBool('generate-init', False).getValue()
        self.dcfile = DCFile()
        self.dcfile.readAll()
        self.classesTuples = []
        self.dclass2module = {}
        self.className2Fields = {}
        self.className2ImportSymbol = {}
        self.dclass2subclass = {}
        self.ignoredClasses = []
        if not self.dcfile.allObjectsValid():
            print 'There was an error reading the dcfile!'
            return

        self.readImports()

        if self.generateNonImportDclasses:
            self.readDclasses()
            if not os.path.isdir('output'):
                os.makedirs('./output')
                os.chdir('output')
            else:
                os.chdir('output')

        self.readClasses()
        self.readFields()
        print 'Done.'


    def readImports(self):
        for i in xrange(self.dcfile.getNumImportModules()):
            importModule = self.dcfile.getImportModule(i)
            isImportClass = False
            if '/' in importModule:
                isImportClass = importModule
                modules = [e+'.' for e in importModule.split('.')[:-1] if e != ""]
                importModule = ''.join(modules)[:-1]

            for n in xrange(self.dcfile.getNumImportSymbols(i)):
                symbol = self.dcfile.getImportSymbol(i, n)
                classes = symbol.split('/')
                subclasses = []
                if symbol == '*':
                    print 'Skipping import for %s. Can\'t create classes for wildcard imports!' % importModule
                    continue
                if isImportClass:
                    subclass = isImportClass.split('.')[-1]
                    subclasses = subclass.split('/')
                    if len(subclasses) > 1:
                        for dcClass in subclasses[1:]:
                            subclasses[subclasses.index(dcClass)] = subclasses[0] + dcClass

                if len(classes) > 1:
                    for dcClass in classes[1:]:
                        classes[classes.index(dcClass)] = classes[0] + dcClass

                if isImportClass:
                    for dcClass in classes:
                        self.dclass2subclass[dcClass] = subclasses[classes.index(dcClass)]

                self.classesTuples.append(classes)

                for dcClass in classes:
                    self.dclass2module[dcClass] = importModule

                if importModule.split('.')[0] in ('direct', 'panda3d'):
                    continue

                self.validateModule(importModule)

    def readClasses(self):
        for classes in self.classesTuples:
            for dcClass in classes:
                importModule = self.dclass2module.get(dcClass)
                if not importModule:
                    importLine = 'import %s' % (dcClass)
                else:
                    importLine = 'from %s import %s' % (importModule, dcClass)

                    if importModule.split('.')[0] in ('direct', 'panda3d'):
                        continue

                generated = False
                try:
                    exec importLine
                except Exception as e:
                    if isinstance(e, ImportError):
                        if dcClass in e.message:
                            self.validateClass(dcClass, importModule)
                            generated = True
                finally:
                    if self.wantOverwrite and not generated and dcClass not in self.ignoredClasses:
                        self.validateClass(dcClass, importModule)

    def readDclasses(self):
        for i in xrange(self.dcfile.getNumClasses()):
            dclass = self.dcfile.getClass(i)
            if not dclass.isStruct():
                classes = [dclass.getName(),
                           dclass.getName() + 'AI']
                self.classesTuples.append(classes)
        print self.classesTuples

    def readFields(self):
        for className in self.classesTuples:
            dcClass = self.dcfile.getClassByName(className[0])

            if not dcClass:
                print 'Found import for %s but no dclass defined.' % className
                continue

            print 'Reading fields for dclass %s...' % className[0]
            self.className2Fields[className[0]] = []
            for i in xrange(dcClass.getNumFields()):
                dcField = dcClass.getField(i)
                self.className2Fields[className[0]].append(dcField)

                if self.generateNonImportDclasses:
                    self.generateField(dcField, className[0])
                    continue

                if self.dclass2module[className[0]].split('.')[0] not in ('direct', 'panda3d'):
                    self.generateField(dcField, className[0])

    def validateModule(self, importModule):
        if '/' in importModule:
            print 'FAILED FOR %s' % importModule

            return
        try:
            exec('import %s' % importModule)
        except:
            self.generateModule(importModule)

    def createModuleFolder(self, modulePath):
        try:
            os.makedirs('./' + modulePath)
        except WindowsError:
            folders = modulePath.split('/')[:-1]
            if not folders:
                return
            nextDir = folders[0]
            if not os.path.isdir(nextDir):
                os.makedirs(nextDir)
            os.chdir(nextDir)
            if len(folders) == 1:
                return
            self.createModuleFolder(folders[1])
            os.chdir('..')

    def moveToModulePath(self, modulePath):
        try:
            os.chdir(modulePath)
        except WindowsError:
            directories = modulePath.split('/')
            if os.path.isdir(directories[0]):
                os.chdir(directories[0])
                self.moveToModulePath(directories[1])

    def generateModule(self, module):
        modulePath = module.replace('.', '/')

        if not os.path.isdir(modulePath):
            self.createModuleFolder(modulePath)

        self.moveToModulePath(modulePath)

        if '.' in module:
            for x in xrange(len(module.split('.'))):
                open('./__init__.py', 'w+')
                os.chdir('..')
        else:
            self.writeInitFile(module)

    def writeInitFile(self, module):
        open('./' + module + '/__init__.py', 'w+')

    def validateClass(self, dcClass, importModule):
        for classdel in CLASS_DELIMITERS:
            if self.ignoreTypes[classdel] is True:
                if classdel in dcClass:
                    self.ignoredClasses.append(dcClass)

        if self.ignoreTypes[''] is True:
            if self.isClientFile(dcClass):
                self.ignoredClasses.append(dcClass)

        if dcClass in self.ignoredClasses:
            return

        print 'Generating class %s...' % dcClass
        self.generateClass(importModule, dcClass)

    def generateClass(self, importModule, className):
        if not importModule and self.generateNonImportDclasses:
            directory = '.'
        else:
            directory = importModule.replace('.', '/')

        if not os.path.isdir(directory):
            os.makedirs(directory)

        if className in self.dclass2subclass.keys():
            f = open(
                directory + '/' + self.dclass2subclass[className] + '.py', 'w+'
            )
        else:
            f = open(
                directory + '/' + className + '.py', 'w+'
            )
        dcClassName = className

        for classdel in CLASS_DELIMITERS:
            if classdel in className:
                dcClassName = className.split(classdel)[0]

        dcClass = self.dcfile.getClassByName(dcClassName)

        parentClasses =[]
        file = ""
        if dcClass:
            for i in xrange(dcClass.getNumParents()):
                parentClass = dcClass.getParent(i).getName()

                for classdel in CLASS_DELIMITERS:
                    if classdel in className:
                        parentClass += classdel

                if parentClass not in self.dclass2module.keys() and parentClass not in IMPORTS:
                    print 'Couldn\'t find defined import %s!' % parentClass
                    baseClass = self.removeDelimiter(parentClass)
                    if baseClass in IMPORTS:
                        parentModule = IMPORTS.get(baseClass)
                        print 'Using assumption parent module %s for parent class %s!' % (parentModule, parentClass)
                        parentClasses.append(parentClass)
                    else:
                        continue

                else:
                    parentClasses.append(parentClass)
                    parentModule = IMPORTS.get(parentClass, self.dclass2module.get(parentClass))

                file += 'from ' + parentModule + '.' + parentClass + ' import ' + parentClass + '\n'
        else:
            print 'Couldn\'t find dclass for %s.' % dcClassName

        file += '\n'
        file += 'class %s%s:\n' % (className, self.formatParentClasses(parentClasses))
        file += '\n'
        if self.wantInit:
            file += INDENT + 'def __init__(self):\n'
            numFields = dcClass.getNumFields()
            for i in xrange(numFields):
                dcField = dcClass.getField(i)
                if dcField.hasDefaultValue():
                    defaultValue = self.getDefaultValueFromField(dcField)
                else:
                    defaultValue = 'None'

                if dcField.getName().startswith('set'):
                    file += INDENT + INDENT + 'self.' + dcField.getName()[3].lower() + dcField.getName()[4:] + ' = '\
                            + defaultValue
                    file += '\n'
            file += INDENT + INDENT + 'return\n'

        f.write(file)
        f.close()

    def getDefaultValueFromField(self, f):
        valueString = f.formatData(f.getDefaultValue())
        try:
            data = valueString.split(' = ')[1].replace(')', '')
        except:
            return 'None'

        if '[' in data:
            return '[]'
        elif '<' in data:
            return 'None'
        else:
            try:
                int(data)
                return '0'
            except:
                pass
            return 'None'

    def formatParentClasses(self, parentClasses):
        if len(parentClasses) == 1:
            if parentClasses:
                return '(%s)' % parentClasses[0]
            return '()'
        return str(tuple(parentClasses)).replace('\'', '')

    def removeDelimiter(self, className):
        return className[:-2]

    def generateField(self, dcField, className):
        if className not in self.dclass2module and self.generateNonImportDclasses:
            fileName = className
        else:
            fileName = self.dclass2module[className].replace('.', '/') + '/' + className
        if dcField.isAirecv():
            for classdel in ('AI', 'UD'):
                if self.ignoreTypes[classdel] is True:
                    continue

                if className + classdel in self.dclass2module.keys():
                    self.writeField(fileName, dcField, classDelimiter=classdel)
                elif self.generateNonImportDclasses and os.path.isfile(className + classdel + '.py'):
                    self.writeField(fileName, dcField, classDelimiter=classdel)
                
        elif dcField.isBroadcast() and not dcField.isClsend():
            for classdel in ('AI', 'UD'):
                if self.ignoreTypes[classdel] is True:
                    continue

                if className + classdel in self.dclass2module.keys():
                    self.writeField(fileName, dcField, classDelimiter=classdel)
                elif self.generateNonImportDclasses and os.path.isfile(className + classdel + '.py'):
                    self.writeField(fileName, dcField, classDelimiter=classdel)

        elif dcField.isClsend() and self.ignoreTypes[''] is False:
            self.writeField(fileName, dcField)
        else:
            for classdel in ('', 'AI', 'UD'):
                if self.ignoreTypes[classdel] is True:
                    continue

                if className + classdel in self.dclass2module.keys():
                    self.writeField(fileName, dcField, classDelimiter=classdel)
                elif self.generateNonImportDclasses and os.path.isfile(className + classdel + '.py'):
                    self.writeField(fileName, dcField, classDelimiter=classdel)

    def writeField(self, fileName, dcField, classDelimiter=''):
            f = open(
                fileName + classDelimiter + '.py', 'r+'
            )
            lines = f.readlines()
            for line, i in zip(lines, xrange(len(lines))):
                if 'def %s' % dcField.getName() in line:
                    if not self.wantOverwrite:
                        f.close()
                        return

            if lines[-1] != '\n':
                lines.append('\n')
            numargs = len(self.getParameterList(dcField))
            if not numargs:
                f.close()
                return
            if self.getParameterList(dcField) == ['']:
                numargs = 0
            print 'Writing field %s for %s...' % (dcField.getName(), dcField.getClass().getName() + classDelimiter)
            lines.append(INDENT + 'def %s%s:\n' % (dcField.getName(), self.getTodoString(numargs)))
            lines.append(INDENT + INDENT + '#' + str(dcField))
            lines.append(INDENT + INDENT + 'return\n')
            f.seek(0, 0)
            f.writelines(lines)
            f.close()

    def getParameterList(self, dcField):
        try:
            return re.sub('\[.*]', '', str(dcField)).split(dcField.getName() + '(')[1].split(')')[0].split(',')
        except:
            return ''

    def getTodoString(self, n):
        if n == 0:
            return '(self)'
        if n == 1:
            return '(self, todo0)'
        s = ['self']
        for i in xrange(n):
            s.append('todo%d' % i)
        return str(tuple(s)).replace('\'', '')

    def isClientFile(self, className):
        return 'AI' not in className and 'UD' not in className

DCStubGenerator('example.prc')


