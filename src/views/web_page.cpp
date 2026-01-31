#include "views/web_page.h"
#include <QUrl>
#include <QIcon>
#include <QWebEngineHistory>
#include <QVariant>
#include <QAuthenticator>
#include <QWebEngineSettings>

WebPage::WebPage(QWidget* parent)
    : QWidget(parent)
    , layout_(new QVBoxLayout(this))
    , web_view_(new QWebEngineView(this))
    , toolbar_(new QToolBar(this))
    , address_bar_(new QLineEdit(this))
{
    // Toolbar actions
    back_action_ = toolbar_->addAction(QIcon::fromTheme("go-previous"), "Back", this, &WebPage::onBack);
    forward_action_ = toolbar_->addAction(QIcon::fromTheme("go-next"), "Forward", this, &WebPage::onForward);
    refresh_action_ = toolbar_->addAction(QIcon::fromTheme("view-refresh"), "Refresh", this, &WebPage::onRefresh);

    address_bar_->setPlaceholderText("https://example.com");
    address_bar_->setFixedWidth(640);
    connect(address_bar_, &QLineEdit::returnPressed, this, &WebPage::onNavigate);

    toolbar_->addWidget(address_bar_);

    layout_->addWidget(toolbar_);
    layout_->addWidget(web_view_);

    setLayout(layout_);

    connect(web_view_, &QWebEngineView::loadFinished, this, &WebPage::onLoadFinished);

    // Allow autoplay / AudioContext creation without a user gesture when
    // appropriate pages require it. This relaxes Chromium's default
    // autoplay policy for embedded content. (If you prefer the stricter
    // default, remove this line.)
    web_view_->page()->settings()->setAttribute(QWebEngineSettings::PlaybackRequiresUserGesture, false);
    // Handle HTTP authentication challenges (Basic/Digest) and respond with
    // provided credentials if available.
    connect(web_view_->page(), &QWebEnginePage::authenticationRequired,
            this, &WebPage::onAuthenticationRequired);
}

WebPage::~WebPage()
{
}

void WebPage::setUrl(const QString& url)
{
    address_bar_->setText(url);
    web_view_->setUrl(QUrl::fromUserInput(url));
}

QString WebPage::url() const
{
    return address_bar_->text();
}

void WebPage::onNavigate()
{
    QString u = address_bar_->text();
    web_view_->setUrl(QUrl::fromUserInput(u));
}

void WebPage::onBack()
{
    if (web_view_->history()->canGoBack()) web_view_->back();
}

void WebPage::onForward()
{
    if (web_view_->history()->canGoForward()) web_view_->forward();
}

void WebPage::onRefresh()
{
    web_view_->reload();
}

void WebPage::onLoadFinished(bool ok)
{
    Q_UNUSED(ok)
    address_bar_->setText(web_view_->url().toString());
    emit pageLoadFinished(ok);
}

void WebPage::getElementOuterHtml(const QString& id)
{
    QString safeId = id;
    safeId.replace('\'', "\\'");
    QString js = QString("(function(){ var el = document.getElementById('%1'); return el ? el.outerHTML : null; })();").arg(safeId);
    if (!web_view_ || !web_view_->page()) {
        emit elementHtmlRetrieved(id, QString());
        return;
    }

    web_view_->page()->runJavaScript(js, [this, id](const QVariant &result) {
        QString html;
        if (!result.isNull()) html = result.toString();
        emit elementHtmlRetrieved(id, html);
    });
}

void WebPage::getCanvasDataUrl(const QString& id)
{
    QString safeId = id;
    safeId.replace('\'', "\\'");
    QString js = QString("(function(){ var c = document.getElementById('%1'); return (c && c.toDataURL) ? c.toDataURL() : null; })();").arg(safeId);
    if (!web_view_ || !web_view_->page()) {
        emit canvasDataUrlRetrieved(id, QString());
        return;
    }

    web_view_->page()->runJavaScript(js, [this, id](const QVariant &result) {
        QString dataUrl;
        if (!result.isNull()) dataUrl = result.toString();
        emit canvasDataUrlRetrieved(id, dataUrl);
    });
}

void WebPage::showOnlyElementById(const QString& id)
{
    QString safeId = id;
    safeId.replace('\'', "\\'");

    // This JS finds the element by id, hides all other elements under body,
    // and shows the requested element and its descendants. It also attempts
    // to keep layout by setting display:block for the target and none for
    // others. Adjust JS if the target requires different display (inline, canvas, etc.).
    QString js = QString(R"JS((function(){
        var el = document.getElementById('%1');
        if(!el) return false;
        // Hide all direct descendants of body except the target (and descendants)
        var all = document.querySelectorAll('body *');
        all.forEach(function(node){
            try {
                if(node === el || el.contains(node)) {
                    node.style.display = '';
                } else {
                    node.style.display = 'none';
                }
            } catch(e) {}
        });
        // Ensure the target is visible (some elements need explicit block)
        try { el.style.display = '';} catch(e){}
        return true;
    })());
    )JS").arg(safeId);

    if (!web_view_ || !web_view_->page()) return;
    web_view_->page()->runJavaScript(js);
}

void WebPage::setDefaultAuthCredentials(const QString& username, const QString& password)
{
    default_auth_username_ = username;
    default_auth_password_ = password;
}

void WebPage::onAuthenticationRequired(const QUrl& requestUrl, QAuthenticator* authenticator)
{
    Q_UNUSED(requestUrl)
    if (!default_auth_username_.isEmpty()) {
        authenticator->setUser(default_auth_username_);
        authenticator->setPassword(default_auth_password_);
    }
}
