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

    web_view_->page()->settings()->setAttribute(QWebEngineSettings::PlaybackRequiresUserGesture, false);

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

