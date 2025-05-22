from burp import IBurpExtender, IMessageEditorTabFactory, IMessageEditorTab, IContextMenuFactory, ITab, IMessageEditorController
from javax.swing import JPanel, JTextField, JTextArea, JButton, JTabbedPane, JLabel, JOptionPane, JMenuItem
from java.awt import BorderLayout, GridLayout
from java.util import ArrayList
from java.awt.event import ActionListener
import json

class BurpExtender(IBurpExtender, IMessageEditorTabFactory, IContextMenuFactory, ITab, ActionListener):
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        self._callbacks.setExtensionName("AutoReplaceX")
        
        # Initialize UI
        self.initUI()
        
        # Register components
        self._callbacks.registerMessageEditorTabFactory(self)
        self._callbacks.registerContextMenuFactory(self)
        
        # Load saved settings
        self.loadSettings()
        
    def initUI(self):
        # Create the main panel
        self._panel = JPanel(BorderLayout())
        
        # Create text fields and areas
        self._cookieField = JTextField(30)
        self._jwtField = JTextField(30)
        self._headersArea = JTextArea(10, 30)
        self._saveButton = JButton("Save")
        self._saveButton.addActionListener(self)
        
        # Create a tabbed pane
        tabbedPane = JTabbedPane()
        tabbedPane.addTab("AutoReplaceX", self.createHeaderManagerTab())
        
        # Add the tabbed pane to the main panel
        self._panel.add(tabbedPane)
        
        # Register the UI tab in Burp
        self._callbacks.addSuiteTab(self)
        
    def createHeaderManagerTab(self):
        panel = JPanel(GridLayout(0, 1))
        
        panel.add(JLabel("Cookies:"))
        panel.add(self._cookieField)
        
        panel.add(JLabel("JWT Token:"))
        panel.add(self._jwtField)
        
        panel.add(JLabel("Custom Headers (one per line):"))
        panel.add(self._headersArea)
        
        panel.add(self._saveButton)
        
        return panel
    
    def actionPerformed(self, event):
        if event.getSource() == self._saveButton:
            self.saveSettings()
            JOptionPane.showMessageDialog(self._panel, "Settings saved!")
    
    def saveSettings(self):
        settings = {
            "cookies": self._cookieField.getText(),
            "jwt": self._jwtField.getText(),
            "headers": self._headersArea.getText()
        }
        self._callbacks.saveExtensionSetting("settings", json.dumps(settings))
    
    def loadSettings(self):
        settings = self._callbacks.loadExtensionSetting("settings")
        if settings:
            settings = json.loads(settings)
            self._cookieField.setText(settings.get("cookies", ""))
            self._jwtField.setText(settings.get("jwt", ""))
            self._headersArea.setText(settings.get("headers", ""))
    
    def createNewInstance(self, controller, editable):
        return HeaderManagerTab(self, controller, editable)
    
    def applyHeaders(self, request):
        requestInfo = self._helpers.analyzeRequest(request)
        headers = requestInfo.getHeaders()
        
        # Only apply custom headers from the _headersArea field
        customHeaders = self._headersArea.getText().split("\n")
        for customHeader in customHeaders:
            if customHeader.strip():
                key = customHeader.split(":")[0].strip()
                headers = [header for header in headers if not header.startswith(key + ":")]
                headers.append(customHeader.strip())
        
        # Rebuild the request
        body = request[requestInfo.getBodyOffset():]
        return self._helpers.buildHttpMessage(headers, body)
    
    def createMenuItems(self, invocation):
        menuItems = ArrayList()
        menuItems.add(JMenuItem("Send to Repeater with Cookie Replacement", actionPerformed=lambda x: self.sendToRepeater(invocation, "cookie")))
        menuItems.add(JMenuItem("Send to Repeater with JWT Replacement", actionPerformed=lambda x: self.sendToRepeater(invocation, "jwt")))
        menuItems.add(JMenuItem("Send to Repeater with Full Header Replacement", actionPerformed=lambda x: self.sendToRepeater(invocation, "full")))
        menuItems.add(JMenuItem("Send Cookie to Extension", actionPerformed=lambda x: self.sendToExtension(invocation, "cookie")))
        menuItems.add(JMenuItem("Send JWT Token to Extension", actionPerformed=lambda x: self.sendToExtension(invocation, "jwt")))
        menuItems.add(JMenuItem("Send Headers to Extension", actionPerformed=lambda x: self.sendToExtension(invocation, "headers")))
        return menuItems
    
    def sendToRepeater(self, invocation, mode):
        messageInfo = invocation.getSelectedMessages()[0]
        request = messageInfo.getRequest()
        modifiedRequest = request  # Start with the original request
        
        if mode == "cookie":
            modifiedRequest = self.applyCookie(modifiedRequest)
        elif mode == "jwt":
            modifiedRequest = self.applyJWT(modifiedRequest)
        elif mode == "full":
            modifiedRequest = self.applyHeaders(modifiedRequest)
        
        self._callbacks.sendToRepeater(
            messageInfo.getHttpService().getHost(),
            messageInfo.getHttpService().getPort(),
            messageInfo.getHttpService().getProtocol() == "https",
            modifiedRequest,
            None
        )
    
    def sendToExtension(self, invocation, mode):
        messageInfo = invocation.getSelectedMessages()[0]
        request = messageInfo.getRequest()
        requestInfo = self._helpers.analyzeRequest(request)
        headers = requestInfo.getHeaders()
        
        if mode == "cookie":
            for header in headers:
                if header.startswith("Cookie:"):
                    self._cookieField.setText(header[len("Cookie: "):])
                    break
        elif mode == "jwt":
            for header in headers:
                if header.startswith("Authorization: Bearer "):
                    self._jwtField.setText(header[len("Authorization: Bearer "):])
                    break
        elif mode == "headers":
            filtered_headers = [h for h in headers if not h.startswith(("Host:", "GET ", "POST "))]
            self._headersArea.setText("\n".join(filtered_headers))
        
        self.saveSettings()
    
    def applyCookie(self, request):
        requestInfo = self._helpers.analyzeRequest(request)
        headers = requestInfo.getHeaders()
        headers = [header for header in headers if not header.startswith("Cookie:")]
        headers.append("Cookie: " + self._cookieField.getText())
        body = request[requestInfo.getBodyOffset():]
        return self._helpers.buildHttpMessage(headers, body)
    
    def applyJWT(self, request):
        requestInfo = self._helpers.analyzeRequest(request)
        headers = requestInfo.getHeaders()
        headers = [header for header in headers if not header.startswith("Authorization:")]
        headers.append("Authorization: Bearer " + self._jwtField.getText())
        body = request[requestInfo.getBodyOffset():]
        return self._helpers.buildHttpMessage(headers, body)
    
    # ITab methods
    def getTabCaption(self):
        return "AutoReplaceX"
    
    def getUiComponent(self):
        return self._panel

class HeaderManagerTab(IMessageEditorTab):
    def __init__(self, extender, controller, editable):
        self._extender = extender
        self._editable = editable
        self._txtInput = JTextArea()
        self._txtInput.setEditable(editable)
    
    def getTabCaption(self):
        return "AutoReplaceX"
    
    def getUiComponent(self):
        return self._txtInput
    
    def isEnabled(self, content, isRequest):
        return isRequest
    
    def setMessage(self, content, isRequest):
        if content is None:
            self._txtInput.setText("")
        else:
            self._txtInput.setText(self._extender._helpers.bytesToString(content))
    
    def getMessage(self):
        return self._extender._helpers.stringToBytes(self._txtInput.getText())
    
    def isModified(self):
        return self._txtInput.getText() != self._extender._helpers.bytesToString(self._currentMessage)
    
    def getSelectedData(self):
        return self._extender._helpers.stringToBytes(self._txtInput.getSelectedText())