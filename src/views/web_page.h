#ifndef WEB_PAGE_H
#define WEB_PAGE_H

#include <QWidget>
#include <QWebEngineView>
#include <QVBoxLayout>
#include <QLineEdit>
#include <QToolBar>
#include <QAction>

class WebPage : public QWidget
{
    Q_OBJECT

public:
    explicit WebPage(QWidget* parent = nullptr);
    ~WebPage();

    void setUrl(const QString& url);
    QString url() const;

    // Retrieve an element's outerHTML by id. Emits `elementHtmlRetrieved` with
    // the id and the resulting HTML (empty if not found).
    Q_SLOT void getElementOuterHtml(const QString& id);

    // Retrieve a canvas element as a data URL by id. Emits
    // `canvasDataUrlRetrieved` with the id and the data URL (empty if not found
    // or not a canvas).
    Q_SLOT void getCanvasDataUrl(const QString& id);

    // Hide all elements except the one with given id (and its children).
    // Useful to show only a canvas or a specific DOM node.
    Q_SLOT void showOnlyElementById(const QString& id);

    // Provide default credentials to respond to HTTP authentication
    // challenges (Basic/Digest). Use only for devices you own/administrate.
    void setDefaultAuthCredentials(const QString& username, const QString& password);

private slots:
    void onNavigate();
    void onBack();
    void onForward();
    void onRefresh();
    void onLoadFinished(bool ok);
    void onAuthenticationRequired(const QUrl& requestUrl, QAuthenticator* authenticator);

signals:
    void elementHtmlRetrieved(const QString& id, const QString& html);
    void canvasDataUrlRetrieved(const QString& id, const QString& dataUrl);
    // Emitted when the underlying QWebEngineView finished loading a page
    void pageLoadFinished(bool ok);

private:
    QVBoxLayout* layout_;
    QWebEngineView* web_view_;
    QToolBar* toolbar_;
    QLineEdit* address_bar_;
    QAction* back_action_;
    QAction* forward_action_;
    QAction* refresh_action_;

    // Stored default credentials to use when an authentication challenge occurs
    QString default_auth_username_;
    QString default_auth_password_;
};

#endif // WEB_PAGE_H
